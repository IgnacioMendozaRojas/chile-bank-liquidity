"""Balance-sheet items and their account codes in the CMF chart of accounts.

Two charts cover 2008 onward: 7-digit codes in millions of pesos (2008-2021) and
9-digit codes in pesos (2022 onward, Compendio de Normas Contables). Each item lists
the codes summed to build it in each chart. Items are kept in CLP billion.
"""

from __future__ import annotations

ITEMS: dict[str, dict[str, list[str]]] = {
    "total_assets": {"old": ["1000000"], "new": ["100000000"]},
    "total_liabilities": {"old": ["2000000"], "new": ["200000000"]},
    "demand_deposits": {"old": ["2100000"], "new": ["241000000"]},
    "checking_accounts": {"old": ["2100100"], "new": ["241000100"]},
    "term_deposits": {"old": ["2200000"], "new": ["242000000"]},
    "debt_issued": {"old": ["2400000"], "new": ["245000000"]},
    "cash_and_bank_deposits": {"old": ["1100000"], "new": ["105000000"]},
    "trading_debt_securities": {"old": ["1150000"], "new": ["112000000"]},
    "fvoci_debt_securities": {"old": ["1350000"], "new": ["122000000"]},
}
SCALE = {"old": 1e-3, "new": 1e-9}  # to CLP billion: old charts in CLP million, new in CLP
NEW_CHART_FROM = (2022, 1)


def chart(year: int, month: int) -> str:
    return "new" if (year, month) >= NEW_CHART_FROM else "old"


def number(text) -> float:
    """CMF amounts: '51847187713806,00' or '41.194,55' -> float."""
    if text is None or text == "":
        return 0.0
    return float(str(text).replace(".", "").replace(",", "."))


def extract(rows: list[dict], year: int, month: int) -> dict[str, float]:
    """Item values (CLP billion) from one bank-month of API rows."""
    c = chart(year, month)
    by_code = {r["CodigoCuenta"].strip(): number(r.get("MonedaTotal")) for r in rows}
    return {item: sum(by_code.get(code, 0.0) for code in codes[c]) * SCALE[c] for item, codes in ITEMS.items()}
