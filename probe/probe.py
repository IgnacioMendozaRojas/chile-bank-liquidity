"""One-off: account codes for key balance-sheet items across chart-of-accounts vintages."""

import os
import re
import time

import requests

KEY = (os.getenv("CMF_API_KEY") or "").strip()
BASE = "https://api.cmfchile.cl/api-sbifv3/recursos_api"
PAT = re.compile(
    r"(?i)^(total activos|total pasivos|efectivo|dep[oó]sitos? y otras (obligaciones|captaciones)|dep[oó]sitos a plazo$|"
    r"cuentas de ahorro|instrumentos|inversiones|bonos|letras|cuentas corrientes|otros saldos vista|otras obligaciones a la vista|"
    r"dep[oó]sitos y captaciones|obligaciones a la vista|banco central|tesorer)"
)
out = ["# Account codes by vintage (bank 001)\n"]
for ym in ["2000/01", "2005/01", "2008/01", "2012/01", "2018/01", "2021/12", "2022/01", "2026/08"]:
    r = requests.get(f"{BASE}/balances/{ym}/instituciones/001", params={"apikey": KEY, "formato": "json"}, timeout=60)
    rows = next(iter(r.json().values()))
    hits = [x for x in rows if PAT.search(x["DescripcionCuenta"].strip())]
    out.append(f"\n## {ym}: {len(rows)} accounts, {len(hits)} shown")
    out += [f"- {x['CodigoCuenta']} {x['DescripcionCuenta'].strip()[:90]} = {x.get('MonedaTotal')}" for x in hits[:45]]
    time.sleep(1)
open("probe/results.md", "w").write("\n".join(out) + "\n")
