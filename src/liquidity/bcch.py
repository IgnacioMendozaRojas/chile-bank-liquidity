"""Banco Central de Chile statistics API (SIETE): monthly and daily series."""

from __future__ import annotations

import os

import pandas as pd
import requests

URL = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"

# System-wide monetary aggregates (stocks, CLP billion), used to check the bank-level data.
SERIES = {
    "system_demand_deposits": "F021.DA.STO.N.CLP.5.M",  # demand and savings deposits other than checking
    "system_checking_accounts": "F021.DCC.STO.N.CLP.5.M",  # checking accounts (D1)
    "system_term_deposits": "F021.DP.STO.N.CLP.5.M",
}


def series(code: str, start: str = "2008-01-01", end: str | None = None, session=None) -> pd.Series:
    params = {
        "user": (os.getenv("BCCH_USER") or "").strip(),
        "pass": (os.getenv("BCCH_PASS") or "").strip(),
        "function": "GetSeries",
        "timeseries": code,
        "firstdate": start,
        "lastdate": end or pd.Timestamp.today().strftime("%Y-%m-%d"),
    }
    js = (session or requests).get(URL, params=params, timeout=120).json()
    if js.get("Codigo") != 0:
        raise RuntimeError(f"BCCh {code}: {js.get('Descripcion')}")
    obs = js["Series"]["Obs"]
    s = pd.Series(
        [float(o["value"]) if o["value"] not in ("NaN", "") else float("nan") for o in obs],
        index=pd.to_datetime([o["indexDateString"] for o in obs], dayfirst=True),
        name=code,
    )
    return s.dropna()


def search(frequency: str, session=None) -> list[dict]:
    """Catalogue of series at a frequency (DAILY, MONTHLY...)."""
    params = {
        "user": (os.getenv("BCCH_USER") or "").strip(),
        "pass": (os.getenv("BCCH_PASS") or "").strip(),
        "function": "SearchSeries",
        "frequency": frequency,
    }
    js = (session or requests).get(URL, params=params, timeout=120).json()
    return js.get("SeriesInfos") or []


# Series found in the catalogue by title, so a renamed code does not break the update.
FIND = {
    "tpm": ("DAILY", r"(?i)tasa de pol[ií]tica monetaria"),
    "bcp_2y": ("DAILY", r"(?i)mercado secundario.*\(BCP\) a 2 a"),
    "bcp_5y": ("DAILY", r"(?i)mercado secundario.*\(BCP\) a 5 a"),
    "bcp_10y": ("DAILY", r"(?i)mercado secundario.*\(BCP\) a 10 a"),
    "bcu_5y": ("DAILY", r"(?i)mercado secundario.*\(BCU\) a 5 a"),
    "bcu_10y": ("DAILY", r"(?i)mercado secundario.*\(BCU\) a 10 a"),
}


def find_codes(catalogue: dict[str, list[dict]]) -> dict[str, tuple[str, str]]:
    """name -> (code, title): the matching series with the longest history."""
    import re

    out = {}
    for name, (freq, pattern) in FIND.items():
        hits = [s for s in catalogue.get(freq, []) if re.search(pattern, s.get("spanishTitle") or "")]
        if hits:
            best = max(
                hits,
                key=lambda s: (
                    pd.to_datetime(s.get("lastObservation"), dayfirst=True)
                    - pd.to_datetime(s.get("firstObservation"), dayfirst=True)
                ),
            )
            out[name] = (best["seriesId"], best["spanishTitle"])
    return out
