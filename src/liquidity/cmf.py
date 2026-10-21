"""CMF bank API (api.cmfchile.cl, SBIF v3): monthly balance sheets by bank."""

from __future__ import annotations

import os
import time

import requests

BASE = "https://api.cmfchile.cl/api-sbifv3/recursos_api"


class CmfApi:
    def __init__(self, key: str | None = None, pause: float = 0.3, retries: int = 4, session=None):
        # the key is stripped: a pasted secret often carries a trailing newline
        self.key = (key or os.getenv("CMF_API_KEY") or "").strip()
        if not self.key:
            raise RuntimeError("CMF_API_KEY is not set")
        self.pause, self.retries = pause, retries
        self.session = session or requests.Session()

    def _get(self, path: str):
        for attempt in range(1, self.retries + 1):
            try:
                r = self.session.get(f"{BASE}/{path}", params={"apikey": self.key, "formato": "json"}, timeout=60)
                r.raise_for_status()
                js = r.json()  # an HTML error page raises here
                time.sleep(self.pause)
                return next(iter(js.values()))
            except (requests.RequestException, ValueError):
                if attempt == self.retries:
                    raise
                time.sleep(2**attempt)
        return None

    def institutions(self, year: int, month: int) -> dict[str, str]:
        rows = self._get(f"balances/{year}/{month:02d}/instituciones")
        return {r["CodigoInstitucion"]: r["NombreInstitucion"].strip() for r in rows}

    def balance(self, year: int, month: int, code: str) -> list[dict]:
        return self._get(f"balances/{year}/{month:02d}/instituciones/{code}")
