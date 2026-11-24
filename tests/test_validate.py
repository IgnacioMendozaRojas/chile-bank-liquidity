import numpy as np
import pandas as pd
import pytest

from liquidity import cost, deposits, forecast, results, validate


def test_readme_markers_are_filled_and_stale_ones_reported():
    text = "Funds hold <!--x:fund_share-->15%<!--/x--> of term deposits."
    assert results.stale(text, {"fund_share": "14%"}) == [("fund_share", "15%", "14%")]
    filled = results.fill(text, {"fund_share": "14%"})
    assert filled == "Funds hold <!--x:fund_share-->14%<!--/x--> of term deposits."
    assert results.stale(filled, {"fund_share": "14%"}) == []
    with pytest.raises(KeyError):
        results.fill("<!--x:unknown-->1<!--/x-->", {})


def test_a_flipped_conclusion_stops_publication():
    old = {"claims": {"pass_through_symmetric": True}}
    new = {"claims": {"pass_through_symmetric": False}}
    assert validate.check_claims(new, old)
    assert validate.check_claims(old, old) == []
    assert validate.check_claims(new, None) == []  # nothing published yet


def test_large_monthly_moves_need_review():
    latest = {
        "metrics": [
            {"id": "demand_deposits_tn", "label": "Demand", "change": 0.12, "period": "2026-09"},
            {"id": "term_deposit_cost", "label": "Cost", "change": -0.002, "period": "2026-09"},
        ]
    }
    errs = validate.check_moves(latest)
    assert len(errs) == 1 and errs[0].startswith("Demand")


def test_revised_history_is_caught(tmp_path, monkeypatch):
    out = tmp_path
    rows = "period,code,name,item,clp_bn\n2026-08,001,A,term_deposits,100.0\n2026-09,001,A,term_deposits,101.0\n"
    (out / "bank_balances.csv").write_text(rows.replace("100.0", "99.0"))
    monkeypatch.setattr(validate, "_base", lambda path, base: rows if path.endswith("bank_balances.csv") else None)
    errs = validate.check_history(out, "HEAD")
    assert len(errs) == 1 and "1 changed" in errs[0]
    (out / "bank_balances.csv").write_text(rows + "2026-10,001,A,term_deposits,102.0\n")  # a new month is fine
    assert validate.check_history(out, "HEAD") == []


def _ecm_costs(up: float, down: float, n: int = 180, seed: int = 1) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2012-04", periods=n, freq="M").astype(str)
    moves = rng.choice([-0.5, 0.0, 0.0, 0.5], size=n)
    tpm = pd.Series(5 + np.cumsum(moves), index=idx)
    c = np.empty(n)
    c[0] = tpm.iloc[0] - 0.5
    for t in range(1, n):
        dr = moves[t]
        c[t] = (
            c[t - 1] + (up if dr > 0 else down) * dr - 0.05 * (c[t - 1] - tpm.iloc[t - 1] + 0.5) + rng.normal(0, 0.02)
        )
    costs = pd.DataFrame({"period": idx, "bank": "System", "term_cost": c, "term_cost_measure": "interest"})
    return costs, tpm


def test_spread_model_tells_symmetric_from_asymmetric_pass_through():
    sym = cost.spread_model(*_ecm_costs(0.6, 0.6)).iloc[0]
    assert abs(sym["diff"]) < 0.1  # (HAC p-values over-reject a little in samples this size)
    assert sym["pass_up"] == pytest.approx(0.6, abs=0.1)
    asym = cost.spread_model(*_ecm_costs(0.8, 0.3)).iloc[0]
    assert asym["diff"] > 0.3 and asym["diff_p_value"] < 0.01
    assert asym["gap_closed_per_month"] > 0


def test_forecast_compare_is_positive_when_the_base_model_is_better():
    rows = []
    rng = np.random.default_rng(0)
    for o in pd.period_range("2015-01", periods=30, freq="Q").astype(str):
        for bank in "ABC":
            e = abs(rng.normal(0.05, 0.01))
            rows += [
                {"origin": o, "bank": bank, "deposits": "demand", "horizon_months": 12, "window": "normal",
                 "model": "ETS", "ape": e},
                {"origin": o, "bank": bank, "deposits": "demand", "horizon_months": 12, "window": "normal",
                 "model": "SARIMAX", "ape": e + 0.02},
            ]  # fmt: skip
    r = forecast.compare(pd.DataFrame(rows)).iloc[0]
    assert r["other"] == "SARIMAX" and r["mean_diff"] == pytest.approx(0.02) and r["p_value"] < 0.001


def test_all_banks_cost_is_blank_when_a_large_bank_has_no_statement():
    periods = pd.period_range("2022-01", periods=6, freq="M").astype(str)
    bal = pd.DataFrame(
        [(p, code, code, k, size) for p in periods for code, size in (("001", 1000.0), ("002", 100.0))
         for k in ("term_deposits", "demand_deposits")],
        columns=["period", "code", "name", "item", "clp_bn"],
    )  # fmt: skip
    rows = []
    for i, p in enumerate(periods, start=1):
        for code in ("001", "002"):
            if code == "002" and p == "2022-06":
                continue  # the smaller bank (9% of deposits) misses June
            rows += [(p, code, code, "term_expense", 5.0 * i), (p, code, code, "term_readjust", 0.0)]
            rows += [(p, code, code, "demand_expense", 0.0), (p, code, code, "demand_readjust", 0.0)]
    inc = pd.DataFrame(rows, columns=["period", "code", "name", "item", "clp_bn"])
    c = cost.cost_series(cost.window_sums(inc), bal, {}).set_index(["bank", "period"])
    assert ("System", "2022-06") not in c.index or np.isnan(c.loc[("System", "2022-06"), "term_expense"])
    assert c.loc[("System", "2022-05"), "term_expense"] == pytest.approx(30 * 12 / 3 / 1100 * 100)  # both banks


def test_excess_needs_a_pre_trend_history():
    idx = pd.period_range("2015-01", periods=100, freq="M").astype(str)
    assert deposits.excess(pd.Series(np.linspace(100, 200, 100), index=idx)) == {}
