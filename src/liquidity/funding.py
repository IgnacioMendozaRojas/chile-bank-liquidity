"""Who funds the banks: the share of each bank's term deposits held by mutual funds.

Fund holdings come from chile-mutual-funds-analytics (deposits and bonds by issuing bank,
monthly since 2019, CMF portfolio files). They are matched to each bank's balance sheet
(CMF, pro forma for mergers) and stressed with the outflows the funds themselves showed:
if funds pulled their deposits from a bank as fast as they did from the whole system in
2020-22, how much of the bank's term funding would go?
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

SOURCE = (
    "https://raw.githubusercontent.com/IgnacioMendozaRojas/chile-mutual-funds-analytics/main/"
    "data/processed/bank_funding_by_type.csv"
)
MAP = Path("config/fund_bank_map.yaml")


def fetch(path: Path, url: str = SOURCE) -> pd.DataFrame:
    df = pd.read_csv(url, dtype={"period": str, "issuer_rut": str})
    df.to_csv(path, index=False)
    return df


def by_bank(holdings: pd.DataFrame, mapping: dict[str, str] | None = None) -> pd.DataFrame:
    """period x CMF code: fund deposits and fund-held bank bonds (CLP billion)."""
    mapping = mapping or yaml.safe_load(MAP.read_text())
    h = holdings.assign(code=holdings["bank"].map(mapping)).dropna(subset=["code"])
    out = h.pivot_table(index=["period", "code"], columns="asset_class", values="clp_bn", aggfunc="sum", fill_value=0)
    return out.rename(columns={"Bank deposits": "fund_deposits", "Bank bonds": "fund_bonds"}).reset_index()


def shares(funds: pd.DataFrame, pro_forma: pd.DataFrame) -> pd.DataFrame:
    """Fund deposits as a share of term deposits, and fund-held bonds as a share of debt issued."""
    bal = pro_forma.pivot_table(index=["period", "code"], columns="item", values="clp_bn").reset_index()
    names = pro_forma.drop_duplicates("code", keep="last").set_index("code")["name"]
    df = funds.merge(bal[["period", "code", "term_deposits", "demand_deposits", "debt_issued"]], on=["period", "code"])
    df["name"] = df["code"].map(names)
    df["fund_share_of_term"] = df["fund_deposits"] / df["term_deposits"]
    df["fund_share_of_deposits"] = df["fund_deposits"] / (df["term_deposits"] + df["demand_deposits"])
    df["fund_share_of_bonds"] = df["fund_bonds"] / df["debt_issued"].where(df["debt_issued"] > 0)
    return df


def run_off(shares_latest: pd.DataFrame, fund_outflows: dict[int, float]) -> pd.DataFrame:
    """Term and total deposits lost if funds withdraw at the observed rates (1, 3, 12 months)."""
    out = shares_latest[["code", "name", "fund_share_of_term", "fund_share_of_deposits"]].copy()
    for h, rate in fund_outflows.items():
        out[f"term_lost_{h}m"] = out["fund_share_of_term"] * rate
        out[f"deposits_lost_{h}m"] = out["fund_share_of_deposits"] * rate
    return out


def fund_outflows(holdings: pd.DataFrame, horizons=(1, 3, 12)) -> dict[int, float]:
    """Worst observed outflow of all fund deposits in banks over each horizon."""
    import numpy as np

    total = holdings[holdings["asset_class"] == "Bank deposits"].groupby("period")["clp_bn"].sum().sort_index()
    months = pd.period_range(total.index[0], total.index[-1], freq="M").astype(str)
    s = np.log(total.reindex(months))  # shift by calendar months, not rows
    return {h: float(1 - np.exp((s - s.shift(h)).min())) for h in horizons}
