"""liquidity data   download new months, Banco Central aggregates, checks."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import checks, data
from .cmf import CmfApi


def _notice(level: str, title: str, msg: str) -> None:
    print(f"::{level} title={title}::{msg}" if os.getenv("GITHUB_ACTIONS") else f"{level}: {title}: {msg}")


def cmd_data(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    added = data.download(
        out / "bank_balances.csv",
        CmfApi(),
        log=lambda m: _notice("notice", "CMF", m) if "not available" in m else print(m),
    )
    _notice("notice", "CMF", f"{len(added)} months added" + (f" ({added[0]} to {added[-1]})" if added else ""))
    bal = data.read(out / "bank_balances.csv")
    if bal.empty:
        _notice("error", "No data", "nothing downloaded; see the CMF notice above")
        return 1
    bc = data.system_aggregates(out / "bcch_aggregates.csv")
    cmp_ = checks.system_vs_bcch(bal, bc)
    cmp_.round(4).to_csv(out / "check_system_vs_bcch.csv")
    m = checks.mergers(bal)
    m.to_csv(out / "mergers.csv", index=False)
    checks.pro_forma(bal, m).to_csv(out / "bank_balances_pro_forma.csv", index=False)
    for k in ("demand", "term"):
        r = cmp_[f"ratio_{k}"]
        g = cmp_[f"growth_gap_{k}"].abs()
        _notice(
            "notice",
            f"Check {k}",
            f"CMF/BCCh level ratio {r.min():.2f}-{r.max():.2f}; "
            f"monthly growth gap median {g.median():.2%}, max {g.max():.2%} ({g.idxmax()})",
        )
    _notice("notice", "Mergers", f"{(m['absorbed_by'] != '').sum()} matched, {(m['absorbed_by'] == '').sum()} exits")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="liquidity")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("data", help="download new months and run the data checks")
    d.add_argument("--out", type=Path, default=Path("data/processed"))
    a = p.parse_args(argv)
    return cmd_data(a.out)


if __name__ == "__main__":
    sys.exit(main())
