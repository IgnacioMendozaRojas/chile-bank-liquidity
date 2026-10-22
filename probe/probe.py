"""One-off: does the CMF API serve income statements, and with which interest-expense accounts?"""

import os
import re
import time

import requests

KEY = (os.getenv("CMF_API_KEY") or "").strip()
BASE = "https://api.cmfchile.cl/api-sbifv3/recursos_api"
PAT = re.compile(r"(?i)inter[eé]s|reajust|dep[oó]sito|captaci|gastos? por")
out = ["# CMF income statement probe\n"]
for ym in ["2010/12", "2021/12", "2022/12", "2026/08"]:
    r = requests.get(f"{BASE}/resultados/{ym}/instituciones/001", params={"apikey": KEY, "formato": "json"}, timeout=60)
    try:
        js = r.json()
        rows = next(iter(js.values()))
    except ValueError:
        out.append(f"\n## {ym}: {r.status_code} not JSON ({r.url.split('?')[0]})")
        continue
    if not isinstance(rows, list):
        out.append(f"\n## {ym}: {r.status_code} {str(js)[:200]}")
        continue
    hits = [x for x in rows if PAT.search(str(x.get("DescripcionCuenta", "")))]
    out.append(f"\n## {ym}: {len(rows)} accounts, {len(hits)} interest/deposit related; keys {list(rows[0])}")
    for x in hits[:40]:
        desc = str(x.get("DescripcionCuenta")).strip()[:90]
        out.append(f"- {x.get('CodigoCuenta')} {desc} = {x.get('MonedaTotal')}")
    time.sleep(1)
open("probe/results.md", "w").write("\n".join(out) + "\n")
