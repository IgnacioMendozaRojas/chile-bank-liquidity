"""Download bank balance sheets month by month into data/processed/bank_balances.csv.

One row per month, bank and item (CLP billion). Months already in the file are
skipped, so the first run builds the history and later runs add the new month.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from . import accounts, bcch
from .cmf import CmfApi

START = (2008, 1)
COLUMNS = ["period", "code", "name", "item", "clp_bn"]


def months(start: tuple[int, int], end: tuple[int, int]) -> Iterator[tuple[int, int]]:
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def last_month(today: dt.date | None = None) -> tuple[int, int]:
    today = today or dt.date.today()
    return (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)


def read(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path, dtype={"code": str, "period": str})


def download(path: Path, api: CmfApi, start=START, end=None, log=print) -> list[str]:
    """Add every missing month between start and end; returns the months added."""
    done = set(read(path)["period"])
    added = []
    for y, m in months(start, end or last_month()):
        label = f"{y}-{m:02d}"
        if label in done:
            continue
        try:
            banks = api.institutions(y, m)
        except Exception as exc:  # noqa: BLE001 - a month not yet published ends the run
            log(f"{label}: not available ({exc.__class__.__name__})")
            break
        rows = []
        for code, name in banks.items():
            values = accounts.extract(api.balance(y, m, code), y, m)
            rows += [(label, code, name, item, round(v, 4)) for item, v in values.items()]
        new = pd.DataFrame(rows, columns=COLUMNS)
        new.to_csv(path, mode="a", header=not Path(path).exists(), index=False)
        added.append(label)
        log(f"{label}: {len(banks)} banks")
    return added


def system_aggregates(path: Path, start: str = "2008-01-01") -> pd.DataFrame:
    """Banco Central monthly deposit aggregates, for the cross-check."""
    out = pd.DataFrame({name: bcch.series(code, start) for name, code in bcch.SERIES.items()})
    out.index = out.index.to_period("M").astype(str)
    out.index.name = "period"
    out.to_csv(path)
    return out
