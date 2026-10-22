"""Deposit behaviour from observed balances: worst outflows, stress outflows, stable core, decay.

For each bank (pro-forma for mergers) and the system, and for demand, term and total
deposits, the h-month log change of the balance is measured over the whole history:

    r_h(t) = ln(D_t / D_{t-h}),   outflow_h = 1 - exp(r_h)

- worst observed outflow per horizon, with the month it ended and the crisis episode;
- the 1st percentile of r_h, as a 99% outflow;
- the stress outflow, the larger of the two, so a crisis in the sample is never averaged away;
- the stable core, 1 - stress outflow at 12 months;
- a decay curve: survival S(h) = 1 - stress outflow over h = 1..24 months, made monotone,
  with an exponential fit S(h) = exp(-lambda h) and its half-life.

Changes are nominal and not detrended, so growth in calm years does not offset a crisis;
seasonal moves (the usual January drop in demand deposits) are part of what a bank must fund.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import checks

EPISODES = {
    "Global financial crisis": ("2008-09", "2009-12"),
    "Social unrest": ("2019-10", "2020-02"),
    "COVID and pension withdrawals": ("2020-03", "2021-12"),
    "Rate hikes": ("2022-01", "2023-12"),
}
SERIES = {"demand": ["demand_deposits"], "term": ["term_deposits"], "total": ["demand_deposits", "term_deposits"]}
HORIZONS = (1, 3, 12)
TOP_BANKS = 10


def episode(period: str) -> str:
    for name, (a, b) in EPISODES.items():
        if a <= period <= b:
            return name
    return "Outside crisis windows"


def balances_by_bank(pro_forma: pd.DataFrame, raw: pd.DataFrame, top: int = TOP_BANKS) -> dict[str, pd.DataFrame]:
    """period x {demand, term, total} for the system (CMF code 999) and the largest banks today."""
    out = {}
    system = raw[raw["code"] == "999"].pivot_table(index="period", columns="item", values="clp_bn")
    out["System"] = pd.DataFrame({k: system[v].sum(axis=1, min_count=len(v)) for k, v in SERIES.items()})
    assets = checks.wide(pro_forma, "total_assets")
    names = pro_forma.drop_duplicates("code", keep="last").set_index("code")["name"]
    for code in assets.iloc[-1].nlargest(top).index:
        b = pro_forma[pro_forma["code"] == code].pivot_table(index="period", columns="item", values="clp_bn")
        out[names[code]] = pd.DataFrame({k: b[v].sum(axis=1, min_count=len(v)) for k, v in SERIES.items()})
    return out


def outflows(balance: pd.Series, horizons=HORIZONS, q: float = 0.01) -> pd.DataFrame:
    """Worst, 99% and stress outflow per horizon for one balance series."""
    s = np.log(balance.where(balance > 0)).dropna()
    rows = []
    for h in horizons:
        r = (s - s.shift(h)).dropna()
        if len(r) < 24:
            continue
        worst_end = r.idxmin()
        worst = 1 - np.exp(r.min())
        p99 = 1 - np.exp(np.quantile(r, q))
        rows.append(
            {
                "horizon_months": h,
                "worst_outflow": worst,
                "worst_ended": worst_end,
                "worst_episode": episode(worst_end),
                "p99_outflow": p99,
                "stress_outflow": max(worst, p99, 0.0),
                "observations": len(r),
            }
        )
    return pd.DataFrame(rows)


def decay(balance: pd.Series, max_h: int = 24, q: float = 0.01) -> dict:
    """Survival curve from stress outflows at every horizon, exponential fit and half-life."""
    s = np.log(balance.where(balance > 0)).dropna()
    surv = []
    for h in range(1, max_h + 1):
        r = (s - s.shift(h)).dropna()
        stress = max(1 - np.exp(r.min()), 1 - np.exp(np.quantile(r, q)), 0.0) if len(r) >= 24 else np.nan
        surv.append(1 - stress)
    surv = pd.Series(surv, index=range(1, max_h + 1)).cummin()  # survival cannot recover with horizon
    ok = surv.dropna()
    lam = float(-np.sum(ok.index * np.log(ok.values)) / np.sum(ok.index**2))  # least squares through S(0)=1
    return {
        "survival": surv,
        "lambda_per_month": lam,
        "half_life_months": np.log(2) / lam if lam > 0 else np.inf,
        "core_12m": float(surv.get(12, np.nan)),
    }


def backtest(balance: pd.Series, split: str = "2019-12", horizons=HORIZONS) -> pd.DataFrame:
    """Stress outflows estimated up to `split` against the worst outflow realised after it."""
    before = outflows(balance[balance.index <= split], horizons)
    s = np.log(balance.where(balance > 0)).dropna()
    rows = []
    for _, row in before.iterrows():
        h = int(row["horizon_months"])
        r = (s - s.shift(h)).dropna()
        after = r[r.index > split]
        realised = 1 - np.exp(after.min()) if len(after) else np.nan
        rows.append(
            {
                "horizon_months": h,
                "stress_estimated_to_2019": row["stress_outflow"],
                "worst_realised_after": max(realised, 0.0),
                "realised_ended": after.idxmin() if len(after) else None,
                "covered": bool(row["stress_outflow"] >= realised),
            }
        )
    return pd.DataFrame(rows)


def run(pro_forma: pd.DataFrame, raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tables = {"outflows": [], "decay": [], "survival": [], "backtest": []}
    for bank, df in balances_by_bank(pro_forma, raw).items():
        for kind in SERIES:
            bal = df[kind].dropna()
            o = outflows(bal).assign(bank=bank, deposits=kind)
            tables["outflows"].append(o)
            d = decay(bal)
            tables["decay"].append(
                pd.DataFrame(
                    [
                        {
                            "bank": bank,
                            "deposits": kind,
                            "core_12m": d["core_12m"],
                            "lambda_per_month": d["lambda_per_month"],
                            "half_life_months": d["half_life_months"],
                            "first_month": bal.index[0],
                            "balance_latest_clp_bn": bal.iloc[-1],
                        }
                    ]
                )
            )
            tables["survival"].append(
                d["survival"]
                .rename("survival")
                .rename_axis("horizon_months")
                .reset_index()
                .assign(bank=bank, deposits=kind)
            )
            tables["backtest"].append(backtest(bal).assign(bank=bank, deposits=kind))
    return {k: pd.concat(v, ignore_index=True) for k, v in tables.items()}
