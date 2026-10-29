"""One-off: how the CMF 'Estados Financieros' page links each month's zip."""

import re

import requests

URL = "https://www.cmfchile.cl/portal/estadisticas/626/w4-propertyvalue-30250.html"
r = requests.get(URL, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
html = r.text
out = [f"# listing probe: HTTP {r.status_code}, {len(html)} chars"]
zips = re.findall(r'href="([^"]+\.zip[^"]*)"', html)
out.append(f"{len(zips)} zip links; first {zips[:3]}; last {zips[-3:]}")
for key in ("julio 2023", "noviembre 2025", "abril 2016", "diciembre 2008"):
    i = html.lower().find(key)
    out.append(f"\n## '{key}' at {i}")
    if i >= 0:
        out.append("```\n" + html[max(0, i - 700) : i + 700] + "\n```")
pages = re.findall(r'href="([^"]*(?:pagina|page|offset|start)[^"]*)"', html, flags=re.I)
out.append(f"\npagination-like links: {pages[:10]}")
open("probe/results.md", "w").write("\n".join(out) + "\n")
