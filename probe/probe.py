"""One-off check of the public sources for this repository. Writes probe/results.md."""

import os
import re

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
out = ["# Source probe\n"]


def get(url, **kw):
    try:
        r = requests.get(url, headers=UA, timeout=60, **kw)
        return r.status_code, r.text
    except Exception as exc:  # noqa: BLE001
        return "ERR", str(exc)


# CMF API (SBIF v3): does a bank balance-sheet resource exist?
for path in ["balances/2024/01/instituciones/001", "resultados/2024/01/instituciones/001"]:
    code, text = get(f"https://api.cmfchile.cl/api-sbifv3/recursos_api/{path}?formato=json")
    out.append(f"- CMF API `{path}`: {code} {text[:160]!r}")

# CMF statistics pages for banks: links to files
for url in [
    "https://www.cmfchile.cl/portal/estadisticas/617/w3-channel.html",
    "https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-28917.html",
]:
    code, html = get(url)
    links = re.findall(r'href="([^"]+)"[^>]*>([^<]{3,120})<', html)
    keep = [(h, t.strip()) for h, t in links if re.search(r"(?i)financ|balance|estado|\.zip|\.xls|\.txt|mensual", h + t)]
    out.append(f"\n## {url} -> {code}, {len(links)} links, {len(keep)} relevant")
    out += [f"- [{t}]({h})" for h, t in keep[:40]]

# Banco Central SIETE API: catalogue search
user, pw = os.getenv("BCCH_USER"), os.getenv("BCCH_PASS")
base = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
words = re.compile(r"(?i)dep[oó]sit|vista|plazo|pol[ií]tica monetaria|BCP|BTP|BCU|BTU|bono|mercado secundario")
for freq in ["MONTHLY", "DAILY"]:
    try:
        r = requests.get(base, params={"user": user, "pass": pw, "function": "SearchSeries", "frequency": freq},
                         timeout=120)
        js = r.json()
        series = js.get("SeriesInfos") or []
        out.append(f"\n## BCCh SearchSeries {freq}: http {r.status_code}, code {js.get('Codigo')}, "
                   f"{js.get('Descripcion')}, {len(series)} series")
        hits = [s for s in series if words.search(s.get("spanishTitle", "") or "")]
        out.append(f"{len(hits)} matching titles; first 60:")
        out += [f"- `{s['seriesId']}` {s['spanishTitle'][:120]} ({s.get('firstObservation')} to {s.get('lastObservation')})"
                for s in hits[:60]]
    except Exception as exc:  # noqa: BLE001
        out.append(f"\n## BCCh {freq}: ERROR {exc}")

open("probe/results.md", "w").write("\n".join(out) + "\n")
print("\n".join(out[:20]))
