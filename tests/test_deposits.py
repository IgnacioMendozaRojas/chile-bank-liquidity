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
