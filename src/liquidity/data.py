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
from .cmf import CmfApi, QuotaExceeded

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


def download(path: Path, api: CmfApi, start=START, end=None, log=print, kind: str = "balances") -> list[str]:
    """Add every missing bank-month between start and end; returns the months with new rows.

    kind "balances" stores balance-sheet items; "resultados" income-statement items.
    Months with a bank left out are listed in <file>_gaps.csv and asked again on the next
    run; complete months are not requested again. A month not yet published (404) or the
    API request limit (420) ends the run; other server errors skip that month or bank.
    """
    fetch, extract = (api.balance, accounts.extract) if kind == "balances" else (api.results, accounts.extract_income)
    have = read(path)
    done = set(zip(have["period"], have["code"], strict=True))
    gaps_path = Path(path).with_name(Path(path).stem + "_gaps.csv")
    gaps = set(pd.read_csv(gaps_path, dtype=str)["period"]) if gaps_path.exists() else set()
    complete = set(have["period"]) - gaps
    per_row = len(accounts.ITEMS if kind == "balances" else accounts.INCOME)
    missing, added = set(), []
    for y, m in months(start, end or last_month()):
        label = f"{y}-{m:02d}"
        if label in complete:
            continue
        quota = False
        rows, failed = [], []
        try:
            banks = api.institutions(y, m, kind)
        except QuotaExceeded as exc:
            log(f"{label}: not available ({exc}); the next run resumes here")
            quota, banks = True, {}
        except Exception as exc:  # noqa: BLE001
            if getattr(getattr(exc, "response", None), "status_code", None) == 404:
                log(f"{label}: not available ({exc!r})"[:400])
                break
            log(f"{label}: no data for the bank list after retries (skipped) {exc!r}"[:400])
            missing.add(label)
            continue
        for code, name in banks.items():
            if (label, code) in done:
                continue
            try:
                values = extract(fetch(y, m, code), y, m)
            except QuotaExceeded as exc:
                log(f"{label}: not available ({exc}); the next run resumes here")
                quota = True
                break
            except Exception:  # noqa: BLE001 - one bank's server error must not stop the history
                failed.append(code)
                continue
            rows += [(label, code, name, item, round(v, 4)) for item, v in values.items()]
        if rows:
            pd.DataFrame(rows, columns=COLUMNS).to_csv(path, mode="a", header=not Path(path).exists(), index=False)
            added.append(label)
            log(f"{label}: {len(rows) // per_row} banks")
        if failed:
            log(f"{label}: no data for {failed} after retries (left out)")
        if failed or quota:
            missing.add(label)
        if quota:
            missing |= {g for g in gaps if g > label}
            break
    pd.DataFrame({"period": sorted(missing)}).to_csv(gaps_path, index=False)
    return added


def system_aggregates(path: Path, start: str = "2008-01-01") -> pd.DataFrame:
    """Banco Central monthly deposit aggregates, for the cross-check."""
    got = {}
    for name, code in bcch.SERIES.items():
        try:
            got[name] = bcch.series(code, start)
        except Exception as exc:  # noqa: BLE001 - a missing series must not stop the update
            print(f"::warning title=BCCh {name}::{exc}")
    out = pd.DataFrame(got)
    out.index = out.index.to_period("M").astype(str)
    out.index.name = "period"
    out.to_csv(path)
    return out


def rates(path: Path, start: str = "2002-01-01") -> pd.DataFrame:
    """Policy rate and secondary-market yields of Central Bank bonds, daily, in percent."""
    catalogue = {"DAILY": bcch.search("DAILY")}
    codes = bcch.find_codes(catalogue)
    got = {}
    for name, (code, title) in codes.items():
        try:
            got[name] = bcch.series(code, start)
            print(f"::notice title=BCCh {name}::{code} {title[:90]}")
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=BCCh {name}::{exc}")
    missing = set(bcch.FIND) - set(codes)
    if missing:
        print(f"::warning title=BCCh not found::{sorted(missing)}")
    out = pd.DataFrame(got).sort_index()
    out.index.name = "date"
    out.to_csv(path)
    return out
