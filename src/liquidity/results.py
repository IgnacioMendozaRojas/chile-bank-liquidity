"""Every figure and conclusion quoted in the README prose, computed from data/processed.

`compute` returns {"facts": {key: text}, "values": {key: number}, "claims": {key: bool}}:
- facts are the exact strings placed between <!--x:key--> and <!--/x--> markers in the README
  (and on the website), so no number in the prose is typed by hand;
- values are the unrounded numbers behind them, for checks;
- claims are the directional conclusions the text rests on. `liquidity validate` stops the
  monthly publication when one of them flips, so a sentence never changes meaning silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .cost import SPREAD_LAGS

MARK = re.compile(r"<!--x:([a-z0-9_]+)-->(.*?)<!--/x-->", re.S)


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _month(p: str) -> str:
    return pd.Period(p, "M").strftime("%B %Y")


def _years(periods) -> str:
    ys = sorted({int(str(p)[:4]) for p in periods})
    return str(ys[0]) if len(ys) == 1 else f"{ys[0]}-{str(ys[-1])[2:]}"


def _read(out: Path, name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(out / f"{name}.csv", dtype={"code": str, "period": str, "origin": str}, **kw)


def compute(out: Path = Path("data/processed")) -> dict:
    from .build import _system_fund_share, short
    from .cost import month_end_rate

    f: dict[str, str] = {}
    v: dict[str, float] = {}
    c: dict[str, bool] = {}

    # ── surge ─────────────────────────────────────────────────────────────
    ex = _read(out, "deposits_excess_series")
    s = ex[(ex["bank"] == "System") & (ex["deposits"] == "demand")].set_index("period")
    ratio = s["actual"] / s["trend"] - 1
    peak = ratio.idxmax()
    v["surge_pct"], v["surge_tn"] = float(ratio[peak]), float((s.loc[peak, "actual"] - s.loc[peak, "trend"]) / 1000)
    f["surge_pct"], f["surge_month"], f["surge_tn"] = _pct(v["surge_pct"]), _month(peak), f"{v['surge_tn']:.0f}"
    f["trend_growth"] = _pct(
        _read(out, "deposits_excess")
        .query("bank == 'System' and deposits == 'demand'")["trend_growth_per_year"]
        .iloc[0]
    )

    # ── stress outflows ───────────────────────────────────────────────────
    o = _read(out, "deposits_outflows")
    o12 = o[o["horizon_months"] == 12].set_index(["bank", "deposits"])
    sd, st = o12.loc[("System", "demand")], o12.loc[("System", "term")]
    v["sys_demand_worst12"], v["sys_term_worst12"] = float(sd["worst_outflow"]), float(st["worst_outflow"])
    f["sys_demand_worst12"], f["sys_demand_worst12_year"] = _pct(sd["worst_outflow"]), sd["worst_ended"][:4]
    f["sys_term_worst12"], f["sys_term_worst12_years"] = (
        _pct(st["worst_outflow"]),
        {
            "COVID and pension withdrawals": "2020-21",
            "Rate hikes": "2022-23",
            "Global financial crisis": "2008-09",
        }.get(st["worst_episode"], st["worst_ended"][:4]),
    )
    f["sys_term_stress_ex_pandemic"] = _pct(st["stress_outflow_ex_pandemic"])
    c["demand_worst_in_rate_hikes"] = sd["worst_episode"] == "Rate hikes"
    c["term_worst_in_pandemic"] = st["worst_episode"] == "COVID and pension withdrawals"
    banks = o12.xs("demand", level="deposits").drop("System")
    hikes = banks[banks["worst_episode"] == "Rate hikes"]
    v["banks_hikes_min"], v["banks_hikes_max"] = (
        float(hikes["worst_outflow"].min()),
        float(hikes["worst_outflow"].max()),
    )
    f["banks_hikes_n"] = str(len(hikes))
    f["banks_hikes_range"] = f"{v['banks_hikes_min']:.0%} to {v['banks_hikes_max']:.0%}"
    f["banks_hikes_years"] = _years(hikes["worst_ended"])

    d = _read(out, "deposits_decay").set_index(["bank", "deposits"])
    f["core_demand"], f["core_term"] = (
        _pct(d.loc[("System", "demand"), "core_12m"]),
        _pct(d.loc[("System", "term"), "core_12m"]),
    )
    f["half_life_demand"] = f"{d.loc[('System', 'demand'), 'half_life_months']:.0f}"
    f["half_life_term"] = f"{d.loc[('System', 'term'), 'half_life_months']:.0f}"

    bt = _read(out, "deposits_backtest")
    cov = bt.groupby(["calibrated_to", "deposits"])["covered"].mean()
    for split, tag in (("2019-12", "2019"), ("2021-12", "2021")):
        for k in ("demand", "term", "total"):
            f[f"bt{tag}_{k}"] = _pct(cov[(split, k)])

    # ── forecasts ─────────────────────────────────────────────────────────
    m = _read(out, "forecast_mape_summary")
    normal = m[(m["deposits"] == "demand") & (m["window"] == "normal")].set_index("model")["12"]
    pand = m[(m["deposits"] == "demand") & (m["window"] == "pandemic")].set_index("model")["12"]
    for k, model in (("ets12", "ETS"), ("sarimax12", "SARIMAX"), ("rw12", "Random walk")):
        v[k] = float(normal[model])
        f[k] = f"{normal[model]:.1%}"
    f["pandemic12_range"] = f"{pand.min():.0%} to {pand.max():.0%}"
    c["ets_best_demand12"] = normal.idxmin() == "ETS"
    dm = _read(out, "forecast_compare")
    dm12 = dm[(dm["deposits"] == "demand") & (dm["horizon_months"] == 12)].set_index("other")
    v["dm_sarimax_p"], v["dm_rw_p"] = float(dm12.loc["SARIMAX", "p_value"]), float(dm12.loc["Random walk", "p_value"])
    c["ets_beats_sarimax_demand12_sig"] = bool(dm12.loc["SARIMAX", "mean_diff"] > 0 and v["dm_sarimax_p"] < 0.05)
    f["dm_sarimax_p"], f["dm_rw_p"] = f"{v['dm_sarimax_p']:.2f}", f"{v['dm_rw_p']:.2f}"
    term = m[(m["deposits"] == "term") & (m["window"] == "normal")].set_index("model")
    best_term = {h: term[h].idxmin() for h in ("1", "3", "6", "12")}
    c["ets_best_term_all_horizons"] = all(b == "ETS" for b in best_term.values())
    f["forecast_headline"] = (
        "Simple beats complex for forecasting"
        if c["ets_best_demand12"] and c["ets_beats_sarimax_demand12_sig"]
        else "No forecasting model is reliably better than a simple one"
    )
    f["forecast_verdict"] = (
        "and the difference with SARIMAX is significant"
        if c["ets_beats_sarimax_demand12_sig"]
        else "but the difference with SARIMAX is not statistically significant"
    )
    f["term_forecast_note"] = (
        "Exponential smoothing is also the most accurate for term deposits at every horizon"
        if c["ets_best_term_all_horizons"]
        else "For term deposits no model wins at every horizon (best at 1, 3, 6 and 12 months: "
        + ", ".join(best_term.values())
        + ")"
    )
    fit = _read(out, "forecast_fit").set_index(["bank", "deposits"])
    ft = fit.loc[("System", "term")]
    fd = fit.loc[("System", "demand")]
    f["tpm_term_effect"] = f"{np.expm1(ft['tpm_semi_elasticity']):.1%}"
    f["tpm_term_se"] = f"{ft['tpm_se'] * 100:.1f}"
    f["withdrawal1"] = _pct(fd["withdrawal_2020-08_effect"])
    f["withdrawal3"] = _pct(fd["withdrawal_2021-05_effect"])

    # ── funding ───────────────────────────────────────────────────────────
    sh = _read(out, "funding_fund_shares")
    sys_share = _system_fund_share(sh)
    lp = sh["period"].max()
    latest = sh[sh["period"] == lp].set_index("name")["fund_share_of_term"]
    v["fund_share"] = float(sys_share[lp])
    f["fund_share"], f["fund_share_month"] = _pct(sys_share[lp]), _month(lp)
    f["fund_banks"] = str(sh[sh["period"] == lp]["code"].nunique())
    f["fund_max_bank"], f["fund_max"] = short(latest.idxmax()), _pct(latest.max())
    f["fund_min_bank"], f["fund_min"] = short(latest.idxmin()), _pct(latest.min())
    hi = sys_share[sys_share.index <= "2021-12"].idxmax()
    lo = sys_share[sys_share.index >= hi].idxmin()
    f["fund_peak"], f["fund_peak_month"] = _pct(sys_share[hi]), _month(hi)
    f["fund_trough"], f["fund_trough_month"] = _pct(sys_share[lo]), _month(lo)
    fo = _read(out, "funding_fund_outflows").set_index("horizon_months")["fund_deposit_outflow"]
    for h in (1, 3, 12):
        f[f"fund_outflow{h}"] = _pct(fo[h])

    # ── cost of funding ───────────────────────────────────────────────────
    b = _read(out, "cost_betas")
    sys_b = b[(b["bank"] == "System") & (b["measure"] == "interest")]
    hike = sys_b[sys_b["direction"] == "hike"]
    hike = hike[hike["start"] == hike["start"].max()].set_index("lag_months")
    cut = sys_b[sys_b["direction"] == "cut"]
    cut = cut[cut["start"] == cut["start"].max()].set_index("lag_months")
    f["hike_years"] = f"{hike['start'].iloc[0][:4]}-{hike['end'].iloc[0][2:4]}"
    f["cut_years"] = f"{cut['start'].iloc[0][:4]}-{cut['end'].iloc[0][2:4]}"
    f["hike_tpm"], f["cut_tpm"] = f"{hike['tpm_change'].iloc[0]:+.2f}", f"{cut['tpm_change'].iloc[0]:+.2f}"
    for lag in (0, 3):
        f[f"beta_hike{lag}"], f[f"beta_cut{lag}"] = f"{hike.loc[lag, 'beta']:.2f}", f"{cut.loc[lag, 'beta']:.2f}"
    earlier = sys_b[
        (sys_b["direction"] == "cut") & (sys_b["start"] < hike["start"].iloc[0]) & (sys_b["lag_months"] == 3)
    ]
    f["earlier_cuts_range"] = f"{earlier['beta'].min():.2f} to {earlier['beta'].max():.2f}"

    cs = _read(out, "cost_series")
    sc = cs[(cs["bank"] == "System") & (cs["term_cost_measure"] == "interest")].set_index("period")["term_cost"]
    tpm = month_end_rate(pd.read_csv(out / "bcch_rates_daily.csv", index_col=0))
    h_end, c_end = hike["end"].iloc[0], cut["end"].iloc[0]
    v["gap_end_hikes"], v["gap_end_cuts"] = float(tpm[h_end] - sc[h_end]), float(tpm[c_end] - sc[c_end])
    f["gap_end_hikes"], f["gap_end_cuts"] = f"{v['gap_end_hikes']:.1f}", f"{v['gap_end_cuts']:.1f}"

    sp = _read(out, "cost_spread_model").set_index("bank")
    ss = sp.loc["System"]
    v["pass_up"], v["pass_down"], v["pass_p"] = float(ss["pass_up"]), float(ss["pass_down"]), float(ss["diff_p_value"])
    f["pass_up"], f["pass_down"], f["pass_p"] = (
        f"{ss['pass_up']:.2f}",
        f"{ss['pass_down']:.2f}",
        f"{ss['diff_p_value']:.2f}",
    )
    f["pass_lags"] = str(SPREAD_LAGS + 1)
    f["gap_closed"] = _pct(ss["gap_closed_per_month"])
    banks_sp = sp.drop("System")
    f["spread_banks"] = str(len(banks_sp))
    f["spread_banks_sig"] = str(int((banks_sp["diff_p_value"] < 0.05).sum()))
    f["spread_banks_up"] = str(int((banks_sp["diff"] > 0).sum()))
    c["pass_through_symmetric"] = bool(v["pass_p"] >= 0.10)
    f["cost_headline"] = (
        "Banks pass rate hikes and cuts on to deposits alike"
        if c["pass_through_symmetric"]
        else (
            "Banks pass on more of the rate hikes than of the cuts"
            if v["pass_up"] > v["pass_down"]
            else "Banks pass on more of the rate cuts than of the hikes"
        )
    )

    lb = b[(b["lag_months"] == 3) & (b["bank"] != "System") & (b["measure"] == "interest")]
    lh = lb[(lb["direction"] == "hike") & (lb["start"] == hike["start"].iloc[0])]
    lc = lb[(lb["direction"] == "cut") & (lb["start"] == cut["start"].iloc[0])]
    v["corr_hike"] = float(lh["beta"].corr(lh["avg_fund_share_of_term"]))
    v["corr_cut"] = float(lc["beta"].corr(lc["avg_fund_share_of_term"]))
    f["corr_hike"], f["corr_cut"] = f"{v['corr_hike']:.2f}", f"{v['corr_cut']:.2f}"
    f["corr_banks"] = str(len(lh))
    c["fund_reliance_goes_with_hike_pass_through"] = v["corr_hike"] > 0
    return {"facts": f, "values": {k: round(x, 6) for k, x in v.items()}, "claims": c}


def fill(text: str, facts: dict[str, str]) -> str:
    """Replace the text between each <!--x:key--> and <!--/x--> marker; unknown keys raise."""

    def sub(mo: re.Match) -> str:
        key = mo.group(1)
        if key not in facts:
            raise KeyError(f"README marker {key!r} has no computed value")
        return f"<!--x:{key}-->{facts[key]}<!--/x-->"

    return MARK.sub(sub, text)


def stale(text: str, facts: dict[str, str]) -> list[tuple[str, str, str]]:
    """(key, published, computed) for every marker whose text differs from the computed value."""
    return [(k, old, facts.get(k, "<missing>")) for k, old in MARK.findall(text) if facts.get(k) != old]
