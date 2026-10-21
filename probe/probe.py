"""One-off check of the CMF API key and bank balance-sheet coverage. Writes probe/results.md."""

import json
import os

import requests

RAW = os.getenv("CMF_API_KEY") or ""
KEY = RAW.strip()
BASE = "https://api.cmfchile.cl/api-sbifv3/recursos_api"
out = ["# CMF API probe\n", f"- key present: {bool(KEY)}, length {len(KEY)}, had surrounding whitespace: {RAW != KEY}, alnum: {KEY.isalnum()}"]


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


import re


def text_of(js):
    if isinstance(js, str) or not isinstance(js, dict):
        t = re.sub(r"<[^>]+>", " ", str(js))
        return re.sub(r"\s+", " ", t)[:300]
    return describe(js)


for path in [
    "dolar",
    "uf",
    "balances/2024/01/instituciones/001",
    "balances/2024/01/instituciones",
    "balance/2024/01/instituciones/001",
    "resultados/2024/01/instituciones/001",
    "perfil/instituciones/2024/01",
    "instituciones",
]:
    r = requests.get(f"{BASE}/{path}", params={"apikey": KEY, "formato": "json"}, timeout=60)
    try:
        body = describe(r.json())
    except ValueError:
        body = "HTML/TEXT: " + text_of(r.text)
    out.append(f"- `{path}` -> {r.status_code} {r.url.split('?')[0]} :: {body}")

code, js = call("balances/2026/08/instituciones/001")
if code == 200 and isinstance(js, dict):
    rows = next(iter(js.values()))
    dep = [r for r in rows if any(w in json.dumps(r, ensure_ascii=False).upper() for w in ("DEPOSITO", "DEPÓSITO", "VISTA", "PLAZO", "EFECTIVO", "INSTRUMENTOS"))]
    out.append(f"\n## Banco 001, 2026-08: {len(rows)} accounts; deposit/cash/securities related ({len(dep)}):")
    out += [f"- {json.dumps(r, ensure_ascii=False)[:220]}" for r in dep[:40]]

open("probe/results.md", "w").write("\n".join(out) + "\n")
print("\n".join(out[:12]))
