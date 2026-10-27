"""Cost of deposit funding and the deposit beta: how much of a policy-rate move reaches deposits.

Interest expense comes from the CMF income statements (year to date, so each month is the
difference with the previous one). The cost of term deposits is the interest paid over the
last three months, annualised, over the average term-deposit balance of the same entity
(balances as reported, not pro forma, so numerator and denominator cover the same bank).

The UF readjustment paid on indexed deposits follows inflation, not the policy rate, so the
cost used for the beta excludes it where the chart of accounts splits it out; earlier
months only report interest and readjustment together and are flagged.

Rate cycles are found in the policy rate itself (turning points of at least 1.5 points).
The beta of a cycle is the change in the cost of deposits over the change in the TPM,
measured at the end of the cycle and 3 and 6 months later, since term deposits reprice
as they mature.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import checks

WINDOW = 3  # months of interest expense in the cost
LAGS = (0, 3, 6)


def monthly_flows(income: pd.DataFrame) -> pd.DataFrame:
    """Year-to-date amounts -> amount of each month; long table period, code, item, clp_bn."""
    w = income.pivot_table(index="period", columns=["code", "item"], values="clp_bn", dropna=False)
    w = w.reindex(pd.period_range(w.index.min(), w.index.max(), freq="M").astype(str))
    per = pd.PeriodIndex(w.index, freq="M")
    prev = w.shift(1)
    prev.loc[np.asarray(per.month == 1)] = 0.0  # year to date: January is its own month
    flows = w - prev
    flows.index.name = "period"
    return flows.stack(["code", "item"], future_stack=True).rename("clp_bn").reset_index().dropna()


def cost_series(flows: pd.DataFrame, balances: pd.DataFrame, codes: dict[str, str]) -> pd.DataFrame:
    """Annualised cost of term and demand deposits (%), by bank and for all banks together.

    For all banks together, a bank enters a month only if its three months of interest and
    its balances are all reported, so a missing statement does not understate the cost.
    """
    out = []
    banks = checks.banks_only(balances)
    fl = flows[flows["code"].map(checks.is_bank)]
    per_bank = {}
    for k in ("term", "demand"):
        avg = checks.wide(banks, f"{k}_deposits").rolling(WINDOW + 1).mean()
        sums = {
            part: fl[fl["item"] == f"{k}_{part}"]
            .pivot_table(index="period", columns="code", values="clp_bn")
            .reindex(index=avg.index, columns=avg.columns)
            .rolling(WINDOW)
            .sum()
            for part in ("expense", "readjust")
        }
        per_bank[k] = (avg, sums["expense"], sums["readjust"])
    for name, sel in [("System", None), *[(n, c) for c, n in codes.items()]]:
        cols = {}
        for k, (avg, exp, adj) in per_bank.items():
            if sel is not None:
                avg, exp, adj = avg[[sel]], exp[[sel]], adj[[sel]]
            ok = exp.notna() & avg.notna()
            base = avg.where(ok).sum(axis=1, min_count=1)
            split = (adj.notna() | ~ok).all(axis=1)  # every bank in the sum reports the readjustment
            cols[f"{k}_expense"] = exp.where(ok).sum(axis=1, min_count=1) * 12 / WINDOW / base * 100
            cols[f"{k}_readjust"] = (adj.where(ok).sum(axis=1) * 12 / WINDOW / base * 100).where(split & ok.any(axis=1))
            cols[f"{k}_cost"] = cols[f"{k}_expense"] - cols[f"{k}_readjust"]
        df = pd.DataFrame(cols).dropna(how="all")
        df["term_cost_measure"] = np.where(df["term_readjust"].notna(), "interest", "interest+readjustment")
        df["term_cost_best"] = df["term_cost"].fillna(df["term_expense"])
        out.append(df.assign(bank=name).rename_axis("period").reset_index())
    return pd.concat(out, ignore_index=True)


def month_end_rate(daily: pd.DataFrame, col: str = "tpm") -> pd.Series:
    """Policy rate at the end of each month: a step series with the exact decided levels."""
    s = daily[col].dropna()
    s.index = pd.to_datetime(s.index)
    m = s.resample("ME").last()
    m.index = m.index.to_period("M").astype(str)
    return m


def cycles(tpm: pd.Series, threshold: float = 1.0, pause: int = 12) -> list[tuple[str, str, str]]:
    """Policy-rate cycles (direction, start, end) from a month-end rate.

    Consecutive moves in the same direction form a cycle while they are less than `pause`
    months apart. The cycle starts the month before its first move and ends in the month of
    its last move; cycles that moved the rate less than `threshold` points are left out.
    """
    s = tpm.dropna()
    d = s.diff()
    moves = [(i, np.sign(d.iloc[i])) for i in range(1, len(s)) if abs(d.iloc[i]) > 1e-9]
    out, group, direction = [], [], 0

    def close():
        if group:
            a, b = group[0] - 1, group[-1]
            if abs(s.iloc[b] - s.iloc[a]) >= threshold:
                out.append(("hike" if s.iloc[b] > s.iloc[a] else "cut", s.index[a], s.index[b]))

    for i, sign in moves:
        if group and (sign != direction or i - group[-1] >= pause):
            close()
            group = []
        direction = sign
        group.append(i)
    close()
    return out


def betas(costs: pd.DataFrame, tpm: pd.Series, cycle_list) -> pd.DataFrame:
    rows = []
    for bank, df in costs.groupby("bank"):
        df = df.set_index("period")
        for direction, a, b in cycle_list:
            if a not in df.index:
                continue
            for lag in LAGS:
                end = str(pd.Period(b, "M") + lag)
                if end not in df.index:
                    continue
                d_tpm = tpm[b] - tpm[a]
                rows.append(
                    {
                        "bank": bank,
                        "cycle": f"{direction} {a} to {b}",
                        "direction": direction,
                        "start": a,
                        "end": b,
                        "lag_months": lag,
                        "tpm_change": d_tpm,
                        "cost_change": df.loc[end, "term_cost_best"] - df.loc[a, "term_cost_best"],
                        "measure": "interest"
                        if df.loc[[a, end], "term_cost_measure"].eq("interest").all()
                        else "interest+readjustment",
                    }
                )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["beta"] = out["cost_change"] / out["tpm_change"]
    return out
