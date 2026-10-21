"""One-off check of the CMF API key and bank balance-sheet coverage. Writes probe/results.md."""

import json
import os

import requests

KEY = os.getenv("CMF_API_KEY")
BASE = "https://api.cmfchile.cl/api-sbifv3/recursos_api"
out = ["# CMF API probe\n", f"- key present: {bool(KEY)}"]


def call(path):
    r = requests.get(f"{BASE}/{path}", params={"apikey": KEY, "formato": "json"}, timeout=60)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text[:200]


def describe(js):
    if not isinstance(js, dict):
        return repr(js)[:200]
    keys = list(js)
    first = js[keys[0]] if keys else None
    n = len(first) if isinstance(first, list) else "-"
    sample = first[:2] if isinstance(first, list) else first
    return f"top keys {keys}, records {n}, sample {json.dumps(sample, ensure_ascii=False)[:400]}"


for path in [
    "balances/2026/08/instituciones",
    "balances/2026/08/instituciones/001",
    "balances/2008/01/instituciones/001",
    "balances/2005/01/instituciones/001",
    "balances/2000/01/instituciones/001",
]:
    code, js = call(path)
    out.append(f"- `{path}`: {code} {describe(js)}")

code, js = call("balances/2026/08/instituciones/001")
if code == 200 and isinstance(js, dict):
    rows = next(iter(js.values()))
    dep = [r for r in rows if any(w in json.dumps(r, ensure_ascii=False).upper() for w in ("DEPOSITO", "DEPÓSITO", "VISTA", "PLAZO", "EFECTIVO", "INSTRUMENTOS"))]
    out.append(f"\n## Banco 001, 2026-08: {len(rows)} accounts; deposit/cash/securities related ({len(dep)}):")
    out += [f"- {json.dumps(r, ensure_ascii=False)[:220]}" for r in dep[:40]]

open("probe/results.md", "w").write("\n".join(out) + "\n")
print("\n".join(out[:12]))
