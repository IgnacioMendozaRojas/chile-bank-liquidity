import numpy as np
import pandas as pd
import pytest

from liquidity import accounts, cost


def test_income_items_keep_missing_accounts_as_nan():
    old = [{"CodigoCuenta": "4150300", "MonedaTotal": "-1200,00"}]  # no readjustment split
    got = accounts.extract_income(old, 2010, 12)
    assert got["term_expense"] == pytest.approx(1.2)  # CLP million -> billion, sign flipped
    assert np.isnan(got["term_readjust"])
    new = [
        {"CodigoCuenta": "412180000", "MonedaTotal": "-3000000000,00"},
        {"CodigoCuenta": "416180000", "MonedaTotal": "-1000000000,00"},
    ]
    got = accounts.extract_income(new, 2022, 3)
    assert got["term_expense"] == pytest.approx(4.0) and got["term_readjust"] == pytest.approx(1.0)


def test_three_months_from_year_to_date_across_january_and_gaps():
    ytd = pd.DataFrame(
        {
            "period": ["2021-09", "2021-10", "2021-12", "2022-01", "2022-03"],  # Nov and Feb missing
            "code": "001",
            "name": "A",
            "item": "term_expense",
            "clp_bn": [9.0, 10.0, 12.0, 1.0, 3.0],  # one a month
        }
    )
    f = cost.window_sums(ytd).set_index("period")["clp_bn"]
    assert f["2021-12"] == pytest.approx(3.0)  # Oct-Dec: 12 - 9
    assert f["2022-01"] == pytest.approx(3.0)  # Nov-Jan: 1 + 12 - 10
    assert f["2022-03"] == pytest.approx(3.0)  # Jan-Mar: year to date
    assert "2022-02" not in f.index


def test_cycles_group_moves_and_skip_small_ones():
    idx = pd.period_range("2020-01", periods=24, freq="M").astype(str)
    r = pd.Series(3.0, index=idx)
    r.iloc[3:] = 3.5  # small hike, then a 12-month pause
    r.iloc[16:] = 2.5
    r.iloc[17:] = 1.5  # cut of 2 points in two moves
    out = cost.cycles(r)
    assert out == [("cut", idx[15], idx[17])]


def test_beta_is_cost_change_over_rate_change():
    idx = pd.period_range("2021-01", periods=12, freq="M").astype(str)
    tpm = pd.Series([1.0] * 3 + [2.0, 3.0] + [3.0] * 7, index=idx)
    costs = pd.DataFrame(
        {
            "period": idx,
            "bank": "System",
            "term_cost_best": [1.0] * 3 + [1.5, 2.0, 2.2, 2.3, 2.4] + [2.4] * 4,
            "term_cost_measure": "interest",
        }
    )
    b = cost.betas(costs, tpm, cost.cycles(tpm)).set_index("lag_months")
    assert b.loc[0, "beta"] == pytest.approx(0.5)
    assert b.loc[3, "beta"] == pytest.approx(0.7)


def test_cost_is_annualised_interest_over_average_balance():
    periods = pd.period_range("2022-01", periods=6, freq="M").astype(str)
    bal = pd.DataFrame(
        [(p, "001", "A", k, 1200.0) for p in periods for k in ("term_deposits", "demand_deposits")],
        columns=["period", "code", "name", "item", "clp_bn"],
    )
    rows = []
    for i, p in enumerate(periods, start=1):  # 6 a month of interest, 1 of it UF readjustment
        rows += [(p, "001", "A", "term_expense", 6.0 * i), (p, "001", "A", "term_readjust", 1.0 * i)]
        rows += [(p, "001", "A", "demand_expense", 0.0), (p, "001", "A", "demand_readjust", 0.0)]
    inc = pd.DataFrame(rows, columns=["period", "code", "name", "item", "clp_bn"])
    c = cost.cost_series(cost.window_sums(inc), bal, {"001": "A"}).set_index(["bank", "period"])
    assert c.loc[("A", "2022-06"), "term_expense"] == pytest.approx(6.0)  # 6 x 12 / 1200 = 6%
    assert c.loc[("A", "2022-06"), "term_cost"] == pytest.approx(5.0)
    assert c.loc[("System", "2022-06"), "term_cost_best"] == pytest.approx(5.0)
