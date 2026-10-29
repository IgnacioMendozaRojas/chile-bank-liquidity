"""One-off: do the CMF monthly text files have the income-statement accounts the API failed to serve?"""

import io
import re
import zipfile

import requests

FILES = {
    "2023-07": "https://www.cmfchile.cl/portal/estadisticas/626/articles-72974_recurso_1.zip",
    "2025-11": "https://www.cmfchile.cl/portal/estadisticas/626/articles-102413_recurso_1.zip",
    "2026-08": "https://www.cmfchile.cl/portal/estadisticas/626/articles-113894_recurso_1.zip",
}
CODES = re.compile(
    r"^(4150000|4150100|4150151|4150300|4150351|4150352|4150359|412000000|412150000|412180000|416000000|416150000|416180000)\b"
)
out = ["# CMF monthly text files probe"]
for month, url in FILES.items():
    r = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    out.append(f"\n## {month}: HTTP {r.status_code}, {len(r.content)} bytes, {r.headers.get('content-type')}")
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        out.append(r.text[:300])
        continue
    names = z.namelist()
    out.append(f"{len(names)} files, e.g. {names[:12]}")
    for name in names:
        low = name.lower()
        if not any(b in low for b in ("001", "039")):
            continue
        text = z.read(name).decode("latin-1")
        lines = text.splitlines()
        hits = [ln for ln in lines if CODES.match(ln.strip())]
        out.append(f"- {name}: {len(lines)} lines; first: {lines[:2]}")
        out += [f"    {h.strip()[:120]}" for h in hits[:15]]
open("probe/results.md", "w").write("\n".join(out) + "\n")
