import numpy as np
import pandas as pd
import pytest

from liquidity import deposits


def _series(values, start="2008-01"):
    idx = pd.period_range(start, periods=len(values), freq="M").astype(str)
    return pd.Series(values, index=idx, dtype=float)


def test_stress_outflow_keeps_the_worst_crisis():
    # steady 1% monthly growth with one 30% drop over three months in a crisis window
    v = [100 * 1.01**i for i in range(60)]
    for i, k in enumerate(range(20, 23)):  # 2009-09 .. 2009-11
        v[k] = v[19] * (0.89 ** (i + 1))
    for k in range(23, 60):
        v[k] = v[22] * 1.01 ** (k - 22)
    o = deposits.outflows(_series(v)).set_index("horizon_months")
    assert o.loc[3, "worst_outflow"] == pytest.approx(1 - 0.89**3, rel=1e-6)
    assert o.loc[3, "worst_episode"] == "Global financial crisis"
    assert (o["stress_outflow"] >= o["worst_outflow"]).all()


def test_decay_curve_is_monotone_and_fits_a_known_rate():
    rng = np.random.default_rng(0)
    v = 100 * np.exp(np.cumsum(-0.02 + 0.001 * rng.standard_normal(120)))  # ~2% a month, steady decline
    d = deposits.decay(_series(v))
    assert (d["survival"].diff().dropna() <= 1e-12).all()
    assert d["lambda_per_month"] == pytest.approx(0.02, abs=0.004)
    assert d["half_life_months"] == pytest.approx(np.log(2) / d["lambda_per_month"])


def test_backtest_flags_an_outflow_the_history_did_not_cover():
    v = [100.0] * 144 + [100.0 * 0.95**i for i in range(1, 13)]  # flat to 2019, then a 5% monthly run
    b = deposits.backtest(_series(v)).set_index("horizon_months")
    assert not b.loc[1, "covered"] and b.loc[1, "worst_realised_after"] == pytest.approx(0.05)


def test_pandemic_window_can_be_left_out():
    v = [100 * 1.005**i for i in range(180)]
    k = 12 * 12 + 4  # 2020-05: a 20% one-month drop inside the window
    v = v[:k] + [x * 0.8 for x in v[k:]]
    s = _series(v)
    full = deposits.outflows(s).set_index("horizon_months")
    ex = deposits.outflows(s, exclude=("2020-03", "2021-12")).set_index("horizon_months")
    assert full.loc[1, "worst_outflow"] == pytest.approx(1 - 0.8 * 1.005, rel=1e-6)
    assert ex.loc[1, "worst_outflow"] < 0.01


def test_excess_deposits_over_the_pre_pandemic_trend():
    v = [100 * 1.005**i for i in range(170)]  # 2008-01 onward, 0.5% a month
    for k in range(147, 160):  # 2020-04 .. 2021-04: 15% above trend
        v[k] *= 1.15
    e = deposits.excess(_series(v))
    assert e["peak_excess_pct_of_trend"] == pytest.approx(0.15, abs=0.01)
    assert abs(e["excess_latest_pct_of_trend"]) < 0.01
