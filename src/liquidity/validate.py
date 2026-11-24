"""Checks that must pass before anything is published (`liquidity validate`).

Run by model.yml after `liquidity build` and before the commit, and by CI on every push.
Each failed check prints a ::error annotation and the command exits 1, so the monthly
workflow stops instead of publishing a broken or silently changed number.

Changes that are real but need a human look (a big monthly move, a revised history, a
conclusion that flips) also stop the run; re-run the workflow by hand with
`accept_changes` once they have been reviewed (ACCEPT_CHANGES=1).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path

import pandas as pd

from . import results
from .build import readme_block

# thresholds, documented in the README
MAX_DEPOSIT_MOVE = 0.10  # month-on-month change in system demand or term deposits
MAX_COST_MOVE = 0.01  # month-on-month change in the cost of term deposits (share)
MAX_FUND_SHARE_MOVE = 0.03
MAX_BANKS_VS_CMF_TOTAL = 0.005  # sum of banks vs the CMF's own system total, last 12 months
MAX_GROWTH_GAP_BCCH = 0.05  # monthly growth, CMF vs Banco Central aggregates, latest month
HISTORY_TOLERANCE = 1e-6
HISTORY_FILES = {
    "bank_balances.csv": ["period", "code", "item"],
    "bank_income.csv": ["period", "code", "item"],
    "fund_holdings_by_bank.csv": ["period", "issuer_rut", "asset_class"],
}


def _base(path: str, base: str) -> str | None:
    try:
        return subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def check_markers(readme: str, res: dict, latest: dict) -> list[str]:
    errs = [f"README {k}: published {old!r}, computed {new!r}" for k, old, new in results.stale(readme, res["facts"])]
    if readme_block(latest) not in readme:
        errs.append("README 'Latest reading' table differs from latest.json")
    return errs


def check_claims(res: dict, base_res: dict | None) -> list[str]:
    if not base_res:
        return []
    old = base_res.get("claims", {})
    return [
        f"conclusion {k!r} changed from {old[k]} to {v}: the README wording changes with it"
        for k, v in res["claims"].items()
        if k in old and old[k] != v
    ]


def check_moves(latest: dict) -> list[str]:
    errs = []
    lim = {
        "demand_deposits_tn": MAX_DEPOSIT_MOVE,
        "term_deposits_tn": MAX_DEPOSIT_MOVE,
        "term_deposit_cost": MAX_COST_MOVE,
        "fund_share_of_term": MAX_FUND_SHARE_MOVE,
    }
    for m in latest["metrics"]:
        if m["id"] in lim and abs(m["change"]) > lim[m["id"]]:
            errs.append(f"{m['label']} moved {m['change']:+.2%} in {m['period']} (limit {lim[m['id']]:.0%})")
    return errs


def check_reconciliation(out: Path) -> list[str]:
    errs = []
    t = pd.read_csv(out / "check_banks_vs_system_total.csv", index_col=0).tail(12)
    for col in ("demand_deposits", "term_deposits", "total_assets"):
        worst = t[col].abs().max()
        if worst > MAX_BANKS_VS_CMF_TOTAL:
            errs.append(f"sum of banks vs CMF total, {col}: {worst:.2%} off in the last 12 months")
    b = pd.read_csv(out / "check_system_vs_bcch.csv", index_col=0)
    for k in ("demand", "term"):
        g = abs(b[f"growth_gap_{k}"].dropna().iloc[-1])
        if g > MAX_GROWTH_GAP_BCCH:
            errs.append(f"{k} deposits grew {g:.1%} differently from the Banco Central aggregate in {b.index[-1]}")
    return errs


def check_coverage(out: Path, latest: dict) -> list[str]:
    errs = []
    as_of = latest["as_of"]
    for f in ("bank_balances_gaps.csv", "bank_income_gaps.csv"):
        p = out / f
        if p.exists() and as_of in set(pd.read_csv(p, dtype=str)["period"]):
            errs.append(f"{as_of} has banks missing ({f})")
    for m in latest["metrics"]:
        lag = (pd.Period(as_of, "M") - pd.Period(m["period"], "M")).n
        if lag > 1:
            errs.append(f"{m['label']} is {lag} months behind ({m['period']} vs {as_of})")
    return errs


def check_ranges(out: Path, latest: dict) -> list[str]:
    errs = []
    b = pd.read_csv(out / "cost_betas.csv")
    recent = b[(b["measure"] == "interest") & (b["bank"] == "System")]
    bad = recent[(recent["beta"] < 0) | (recent["beta"] > 1.5)]
    errs += [f"system beta {r['beta']:.2f} out of range ({r['cycle']}, {r['lag_months']} m)" for _, r in bad.iterrows()]
    sh = pd.read_csv(out / "funding_fund_shares.csv")
    if not sh["fund_share_of_term"].between(0, 1).all():
        errs.append("a fund share of term deposits is outside 0-100%")
    sp = pd.read_csv(out / "cost_spread_model.csv")
    if not sp[["pass_up", "pass_down"]].stack().between(-0.5, 1.5).all():
        errs.append("spread model pass-through outside -0.5 to 1.5")
    daily = pd.read_csv(out / "bcch_rates_daily.csv", index_col=0)["tpm"].dropna()
    tpm = {m["id"]: m for m in latest["metrics"]}["policy_rate"]
    month_end = daily[daily.index.str[:7] <= tpm["period"]].iloc[-1] / 100
    if abs(month_end - tpm["value"]) > 1e-9:
        errs.append(f"published TPM {tpm['value']:.2%} differs from the Banco Central series {month_end:.2%}")
    return errs


def check_history(out: Path, base: str) -> list[str]:
    errs = []
    for name, keys in HISTORY_FILES.items():
        path = out / name
        old = _base(str(path), base)
        if old is None or not path.exists():
            continue
        dtype = {k: str for k in keys}
        a = pd.read_csv(io.StringIO(old), dtype=dtype)
        b = pd.read_csv(path, dtype=dtype)
        m = a.merge(b, on=keys, how="left", suffixes=("_old", "_new"))
        val = [c[:-4] for c in m.columns if c.endswith("_old") and m[c].dtype.kind == "f"][0]
        o, n = m[f"{val}_old"], m[f"{val}_new"]
        gone = n.isna() & o.notna()
        moved = (o - n).abs() > HISTORY_TOLERANCE * o.abs().clip(lower=1)
        if gone.any() or moved.any():
            periods = sorted(set(m.loc[gone | moved, "period"]))
            errs.append(
                f"{name}: {int(gone.sum())} published rows removed and {int(moved.sum())} changed "
                f"({periods[0]} to {periods[-1]})"
            )
    return errs


def run(
    out: Path = Path("data/processed"), readme: Path = Path("README.md"), base: str | None = None
) -> tuple[list[str], list[str]]:
    """(errors, accepted): errors stop publication; accepted are reviewed changes let through."""
    base = base or os.getenv("VALIDATE_BASE", "HEAD")
    latest = json.loads(Path("latest.json").read_text(encoding="utf-8"))
    res = json.loads(Path("results.json").read_text(encoding="utf-8"))
    fresh = results.compute(out)
    errs = []
    if fresh["facts"] != res["facts"]:
        errs.append("results.json is out of date: run `liquidity build`")
    base_res = _base("results.json", base)
    hard = check_markers(readme.read_text(encoding="utf-8"), res, latest)
    hard += check_reconciliation(out) + check_coverage(out, latest) + check_ranges(out, latest)
    review = check_claims(res, json.loads(base_res) if base_res else None)
    review += check_moves(latest) + check_history(out, base)
    if os.getenv("ACCEPT_CHANGES") == "1":
        review = [f"accepted after review: {e}" for e in review]
        return errs + hard, review
    return errs + hard + review, []
