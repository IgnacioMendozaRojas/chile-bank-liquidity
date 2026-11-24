"""Real lines from the CMF monthly files (public data), one statement in each chart of accounts.

Banco de Chile's income statement for December 2019 (2008-2021 chart, CLP million, one column per
currency) and September 2026 (2022+ chart, CLP, one column), as published in the zips on the CMF
page "Estados Financieros". Expected values are those stored in data/processed/bank_income.csv,
which came from the API, so the fallback and the API give the same figures.
"""

import io
import zipfile

import pytest

from liquidity import accounts, textfiles

OLD = (
    "001\tBANCO DE CHILE\n"
    "4150000\t-0000000215331,00\t-0000000417206,00\t-0000000000004,00\t-0000000109729,00\n"
    "4150100\t-0000000000539,00\t-0000000013869,00\t 0000000000000,00\t 0000000000000,00\n"
    "4150151\t 0000000000000,00\t-0000000013869,00\t 0000000000000,00\t 0000000000000,00\n"
    "4150300\t-0000000224658,00\t-0000000058175,00\t 0000000000000,00\t-0000000030309,00\n"
    "4150351\t 0000000000000,00\t-0000000039492,00\t 0000000000000,00\t 0000000000000,00\n"
    "4150352\t 0000000000000,00\t-0000000005203,00\t 0000000000000,00\t 0000000000000,00\n"
    "4150359\t 0000000000000,00\t-0000000000043,00\t 0000000000000,00\t 0000000000000,00\n"
)
NEW = (
    "001\tBANCO DE CHILE\n"
    "412000000\t-00707961687956\n"
    "416000000\t-00370139522476\n"
    "412150000\t-00001067057600\n"
    "416150000\t-00013159317411\n"
    "412180000\t-00441367965418\n"
    "416180000\t-00047153462332\n"
)


def _zip(name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text.encode("latin-1"))
    return buf.getvalue()


@pytest.mark.parametrize(
    "period, text, expected",
    [
        (
            "2019-12",
            OLD,
            {
                "term_expense": 313.142,
                "term_readjust": 44.738,
                "demand_expense": 14.408,
                "demand_readjust": 13.869,
                "interest_expense": 742.27,
            },
        ),
        (
            "2026-09",
            NEW,
            {
                "term_expense": 488.5214,
                "term_readjust": 47.1535,
                "demand_expense": 14.2264,
                "demand_readjust": 13.1593,
                "interest_expense": 1078.1012,
            },
        ),
    ],
)
def test_real_statements_match_the_api_figures(period, text, expected):
    rows = textfiles.statement(_zip(f"r1{period.replace('-', '')}001.txt", text), period, "001")
    y, m = map(int, period.split("-"))
    got = accounts.extract_income(rows, y, m)
    for item, value in expected.items():
        assert got[item] == pytest.approx(value, abs=1e-3), item
