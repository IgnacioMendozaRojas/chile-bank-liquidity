"""CMF bank API (api.cmfchile.cl, SBIF v3): monthly balance sheets and income statements by bank."""

from __future__ import annotations

import os
import time

import requests

BASE = "https://api.cmfchile.cl/api-sbifv3/recursos_api"


# The CMF allows 10,000 requests a month per key (HTTP 420 beyond that, until the month ends).
MONTHLY_QUOTA = 10_000
RUN_BUDGET = 3_000  # per workflow run, so one run can never use up the month


class QuotaExceeded(RuntimeError):
    """HTTP 420, or this run's own budget spent: stop instead of retrying."""


class CmfApi:
    def __init__(
        self, key: str | None = None, pause: float = 0.3, retries: int = 4, session=None, budget: int = RUN_BUDGET
    ):
        # the key is stripped: a pasted secret often carries a trailing newline
        self.key = (key or os.getenv("CMF_API_KEY") or "").strip()
        if not self.key:
            raise RuntimeError("CMF_API_KEY is not set")
        self.pause, self.retries = pause, retries
        self.budget, self.used = budget, 0
        self.session = session or requests.Session()

    def _get(self, path: str):
        for attempt in range(1, self.retries + 1):
            if self.used >= self.budget:
                raise QuotaExceeded(f"run budget of {self.budget} requests spent")
            self.used += 1
            try:
                r = self.session.get(f"{BASE}/{path}", params={"apikey": self.key, "formato": "json"}, timeout=60)
                if r.status_code == 420:
                    raise QuotaExceeded(f"CMF request limit reached at {path}")
                r.raise_for_status()
                js = r.json()  # an HTML error page raises here
                time.sleep(self.pause)
                return next(iter(js.values()))
            except (requests.RequestException, ValueError):
                if attempt == self.retries:
                    raise
                time.sleep(2**attempt)
        return None

    def institutions(self, year: int, month: int, kind: str = "balances") -> dict[str, str]:
        rows = self._get(f"{kind}/{year}/{month:02d}/instituciones")
        out = {}
        for r in rows:  # field names vary across years (NombreInstitucion, NombreBanco...)
            code = next(v for k, v in r.items() if k.startswith("Codigo"))
            name = next((v for k, v in r.items() if k.startswith("Nombre")), code)
            out[str(code).strip()] = str(name).strip()
        return out

    def balance(self, year: int, month: int, code: str) -> list[dict]:
        return self._get(f"balances/{year}/{month:02d}/instituciones/{code}")

    def results(self, year: int, month: int, code: str) -> list[dict]:
        """Income statement, year to date."""
        return self._get(f"resultados/{year}/{month:02d}/instituciones/{code}")
