import numpy as np
import pandas as pd
import pytest

from liquidity import forecast


def test_tpm_semi_elasticity_is_recovered():
    rng = np.random.default_rng(1)
    idx = pd.period_range("2008-01", "2026-08", freq="M").astype(str)
    tpm = pd.Series(np.clip(np.cumsum(rng.normal(0, 0.4, len(idx))) + 4, 0.5, 11), index=idx)
    # deposits grow 0.8% a month and fall 3% for each point of TPM
    logd = 10 + 0.008 * np.arange(len(idx)) - 0.03 * tpm.values + np.cumsum(rng.normal(0, 0.003, len(idx)))
    bal = pd.Series(np.exp(logd), index=idx)
    errors, fit = forecast.evaluate(bal, tpm, first_origin="2022-12", step=6)
    assert fit["tpm_semi_elasticity"] == pytest.approx(-0.03, abs=0.01)
    assert set(errors["model"]) == {"SARIMAX", "ETS", "Random walk"}


def test_outlook_runs_from_the_last_month():
    idx = pd.period_range("2015-01", "2026-08", freq="M").astype(str)
    tpm = pd.Series(np.linspace(3, 5, len(idx)), index=idx)
    bal = pd.Series(np.exp(10 + 0.005 * np.arange(len(idx))), index=idx)
    out = forecast.outlook(bal, tpm, "(1, 1, 0)", steps=3)
    assert list(out.index) == ["2026-09", "2026-10", "2026-11"]
    assert (out["low_90"] <= out["forecast"]).all() and (out["forecast"] <= out["high_90"]).all()
