"""Fallback source: the CMF's monthly text files of bank financial statements.

The CMF publishes, besides the API, one zip a month with each bank's balance sheet (b1),
income statement (r1) and other schedules as text: a header line with the bank code and
name, then one line per account (code, tab, amount). When the API fails on a bank-month
(a server error that repeats on every attempt), the income statement is read from here.
The files are listed on the CMF statistics page "Estados Financieros"; they do not count
against the API's request quota.
"""

from __future__ import annotations

import io
import re
import zipfile

import requests

PAGE = "https://www.cmfchile.cl/portal/estadisticas/626/w4-propertyvalue-30250.html"
BASE = "https://www.cmfchile.cl/portal/estadisticas/626/"
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ]
    )
}
LINK = re.compile(r'href="(articles-\d+_recurso_1\.zip)[^"]*"[^>]*aria-label="Descargar (\w+) (\d{4}) \(zip', re.I)


def index(html: str) -> dict[str, str]:
    """'2023-07' -> zip URL; the first link listed for a month is kept."""
    out: dict[str, str] = {}
    for href, month, year in LINK.findall(html):
        m = MONTHS.get(month.lower().replace("setiembre", "septiembre"))
        if m:
            out.setdefault(f"{year}-{m:02d}", BASE + href)
    return out


def statement(zip_bytes: bytes, period: str, code: str, schedule: str = "r1") -> list[dict]:
    """One bank's schedule from a month's zip, as API-like rows {CodigoCuenta, MonedaTotal}."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    target = f"{schedule}{period.replace('-', '')}{code}.txt"
    name = next((n for n in z.namelist() if n.lower().endswith(target)), None)
    if name is None:
        raise KeyError(f"{target} not in the zip")
    rows = []
    for line in z.read(name).decode("latin-1").splitlines()[1:]:  # first line: code and name
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) >= 2 and parts[0].isdigit():
            rows.append({"CodigoCuenta": parts[0], "MonedaTotal": parts[1]})
    return rows


class MonthlyFiles:
    """Downloads the listing once and each month's zip at most once per run."""

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self._index: dict[str, str] | None = None
        self._zips: dict[str, bytes] = {}

    def _get(self, url: str) -> requests.Response:
        r = self.session.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return r

    def results(self, period: str, code: str) -> list[dict]:
        if self._index is None:
            self._index = index(self._get(PAGE).text)
        if period not in self._zips:
            self._zips[period] = self._get(self._index[period]).content
        return statement(self._zips[period], period, code, "r1")
