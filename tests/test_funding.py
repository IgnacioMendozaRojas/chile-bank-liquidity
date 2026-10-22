import pandas as pd
import pytest

from liquidity import funding


def test_fund_share_and_run_off():
    holdings = pd.DataFrame(
        [
            ("2021-01", "97006000", "BCI", "Bank deposits", 10.0),
            ("2021-01", "97006000", "BCI", "Bank bonds", 4.0),
            ("2021-01", "97053000", "Security", "Bank deposits", 2.0),
            ("2021-02", "97006000", "BCI", "Bank deposits", 5.0),
        ],
        columns=["period", "issuer_rut", "bank", "asset_class", "clp_bn"],
    )
    pf = pd.DataFrame(
        [
            ("2021-01", "016", "BCI", "term_deposits", 40.0),
            ("2021-01", "016", "BCI", "demand_deposits", 60.0),
            ("2021-01", "016", "BCI", "debt_issued", 20.0),
            ("2021-01", "028", "BANCO BICE", "term_deposits", 20.0),
            ("2021-01", "028", "BANCO BICE", "demand_deposits", 5.0),
            ("2021-01", "028", "BANCO BICE", "debt_issued", 0.0),
        ],
        columns=["period", "code", "name", "item", "clp_bn"],
    )
    f = funding.by_bank(holdings, {"BCI": "016", "Security": "028"})
    s = funding.shares(f, pf).set_index("code")
    assert s.loc["016", "fund_share_of_term"] == pytest.approx(0.25)
    assert s.loc["016", "fund_share_of_bonds"] == pytest.approx(0.2)
    assert s.loc["028", "fund_share_of_term"] == pytest.approx(0.1)  # Security folded into BICE
    out = funding.fund_outflows(holdings, horizons=(1,))
    assert out[1] == pytest.approx(1 - 5 / 12)
    r = funding.run_off(s.reset_index(), {1: 0.25}).set_index("code")
    assert r.loc["016", "term_lost_1m"] == pytest.approx(0.0625)
