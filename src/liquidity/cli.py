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
    data.rates(out / "bcch_rates_daily.csv")
    cmp_ = checks.system_vs_bcch(bal, bc)
    cmp_.round(4).to_csv(out / "check_system_vs_bcch.csv")
    checks.system_total(bal).to_csv(out / "check_banks_vs_system_total.csv")
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


def cmd_deposits(out: Path) -> int:
    from . import deposits

    raw = data.read(out / "bank_balances.csv")
    pf = data.read(out / "bank_balances_pro_forma.csv")
    for name, table in deposits.run(pf, raw).items():
        table.round(4).to_csv(out / f"deposits_{name}.csv", index=False)
    return 0


def cmd_forecast(out: Path) -> int:
    import pandas as pd

    from . import deposits, forecast

    raw = data.read(out / "bank_balances.csv")
    pf = data.read(out / "bank_balances_pro_forma.csv")
    tpm = forecast.monthly_rate(pd.read_csv(out / "bcch_rates_daily.csv", index_col=0))
    errors, fits, outlooks = [], [], []
    for bank, df in deposits.balances_by_bank(pf, raw).items():
        for kind in ("demand", "term"):
            e, fit = forecast.evaluate(df[kind], tpm)
            errors.append(e.assign(bank=bank, deposits=kind))
            fits.append({"bank": bank, "deposits": kind, **fit})
            outlooks.append(
                forecast.outlook(df[kind], tpm, fit["order"]).reset_index().assign(bank=bank, deposits=kind)
            )
            print(f"{bank} {kind}: {fit['order']} beta={fit['tpm_semi_elasticity']:.4f}")
    errors = pd.concat(errors)
    errors.round(5).to_csv(out / "forecast_errors.csv", index=False)
    summary = errors.groupby(["deposits", "window", "model", "horizon_months"])["ape"].median().unstack()
    summary.round(4).to_csv(out / "forecast_mape_summary.csv")
    pd.DataFrame(fits).round(5).to_csv(out / "forecast_fit.csv", index=False)
    pd.concat(outlooks).round(3).to_csv(out / "forecast_outlook.csv", index=False)
    return 0


def cmd_funding(out: Path) -> int:
    import pandas as pd

    from . import funding

    holdings = funding.fetch(out / "fund_holdings_by_bank.csv")
    pf = data.read(out / "bank_balances_pro_forma.csv")
    sh = funding.shares(funding.by_bank(holdings), pf)
    sh.round(5).to_csv(out / "funding_fund_shares.csv", index=False)
    latest = sh[sh["period"] == sh["period"].max()]
    rates = funding.fund_outflows(holdings)
    ro = funding.run_off(latest, rates)
    # does dependence on funds go with a more volatile term-deposit base? (stress outflows from deposits step)
    dep = pd.read_csv(out / "deposits_outflows.csv")
    names = pf.drop_duplicates("code", keep="last").set_index("name")["code"]
    t12 = dep[(dep["deposits"] == "term") & (dep["horizon_months"] == 12)].assign(code=lambda d: d["bank"].map(names))
    avg_share = sh.groupby("code")["fund_share_of_term"].mean().rename("avg_fund_share_of_term")
    ro = ro.merge(avg_share, on="code").merge(t12[["code", "stress_outflow"]], on="code", how="left")
    ro.round(5).to_csv(out / "funding_run_off.csv", index=False)
    pd.Series(rates, name="fund_deposit_outflow").rename_axis("horizon_months").to_csv(
        out / "funding_fund_outflows.csv"
    )
    _notice(
        "notice",
        "Funding",
        f"fund outflows {rates}; corr(avg fund share, term stress outflow) = "
        f"{ro['avg_fund_share_of_term'].corr(ro['stress_outflow']):.2f}",
    )
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="liquidity")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("data", help="download new months and run the data checks")
    d.add_argument("--out", type=Path, default=Path("data/processed"))
    dep = sub.add_parser("deposits", help="outflows, stable core and decay from the downloaded balances")
    dep.add_argument("--out", type=Path, default=Path("data/processed"))
    f = sub.add_parser("forecast", help="SARIMAX with the policy rate vs benchmarks, out of sample")
    f.add_argument("--out", type=Path, default=Path("data/processed"))
    fu = sub.add_parser("funding", help="share of each bank's term deposits held by mutual funds, and run-off")
    fu.add_argument("--out", type=Path, default=Path("data/processed"))
    a = p.parse_args(argv)
    return {"data": cmd_data, "deposits": cmd_deposits, "forecast": cmd_forecast, "funding": cmd_funding}[a.cmd](a.out)


if __name__ == "__main__":
    sys.exit(main())
