"""Cost of deposit funding and the deposit beta: how much of a policy-rate move reaches deposits.

Interest expense comes from the CMF income statements (year to date, so each month is the
difference of two statements). The cost of term deposits is the interest paid over the
last three months, annualised, over the average term-deposit balance of the same entity
(balances as reported, not pro forma, so numerator and denominator cover the same bank).

The UF readjustment paid on indexed deposits follows inflation, not the policy rate, so the
cost used for the beta excludes it where the chart of accounts splits it out; earlier
months only report interest and readjustment together and are flagged.

Rate cycles are found in the policy rate itself (moves of at least 1 point in total).
The beta of a cycle is the change in the cost of deposits over the change in the TPM,
measured at the end of the cycle and 3 and 6 months later, since term deposits reprice
as they mature.

A cycle beta mixes two things: how much of each rate move is passed on, and how far the
cost still was from the policy rate when the cycle ended (term deposits keep repricing
towards the rate after it stops moving). `spread_model` separates them with an error-
correction regression of the monthly change in cost on rises and falls of the TPM and on
last month's gap between cost and TPM, so pass-through of hikes and cuts can be compared
on equal terms.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import checks

WINDOW = 3  # months of interest expense in the cost
COVERAGE = 0.98  # share of deposits that must be reported for an all-banks figure
LAGS = (0, 3, 6)


def window_sums(income: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """Amounts over the last `window` months from year-to-date figures (long table).

    Only the statements of month t, of month t - window and of the previous December are
    needed, so a month the CMF fails to serve in between does not leave a gap.
    """
    w = income.pivot_table(index="period", columns=["code", "item"], values="clp_bn", dropna=False)
    w = w.reindex(pd.period_range(w.index.min(), w.index.max(), freq="M").astype(str))
    per = pd.PeriodIndex(w.index, freq="M")
    before = w.shift(window)
    dec = w.reindex([f"{y - 1}-12" for y in per.year])
    dec.index = w.index
    across = np.asarray((per - window).year != per.year)
    sums = w - before
    sums.loc[across] = (w + dec - before).loc[across]
    sums.index.name = "period"
    return sums.stack(["code", "item"], future_stack=True).rename("clp_bn").reset_index().dropna()


def cost_series(sums: pd.DataFrame, balances: pd.DataFrame, codes: dict[str, str]) -> pd.DataFrame:
    """Annualised cost of term and demand deposits (%), by bank and for all banks together.

    For all banks together, a bank enters a month only if its three months of interest and
    its balances are all reported, so a missing statement does not understate the cost.
    """
    out = []
    banks = checks.banks_only(balances)
    fl = sums[sums["code"].map(checks.is_bank)]
    per_bank = {}
    for k in ("term", "demand"):
        avg = checks.wide(banks, f"{k}_deposits").rolling(WINDOW + 1).mean()
        sums = {
            part: fl[fl["item"] == f"{k}_{part}"]
            .pivot_table(index="period", columns="code", values="clp_bn")
            .reindex(index=avg.index, columns=avg.columns)
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
            # all banks together: left blank when banks without a statement hold over 2% of deposits
            base = base.where(base >= COVERAGE * avg.sum(axis=1, min_count=1))
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


def asymmetry(b: pd.DataFrame, lags=LAGS, n_boot: int = 10_000, seed: int = 0) -> pd.DataFrame:
    """Is pass-through larger in the last hikes than in the cuts that followed? Bank by bank.

    For each bank the gap is beta(hikes) - beta(cuts) for the two most recent cycles measured
    on interest only. The all-banks figure is one number per cycle and has no sampling error to
    speak of; the question is whether banks, taken one by one, pass on hikes more than cuts.
    Inference resamples banks (paired bootstrap of the mean gap) and adds a t-test and the
    count of banks with a positive gap. With ten banks this is evidence across banks, not a
    test of the system figure.
    """
    from scipy import stats

    x = b[(b["measure"] == "interest") & (b["bank"] != "System")]
    rows = []
    for lag in lags:
        y = x[x["lag_months"] == lag]
        last = {d: y[y["direction"] == d]["start"].max() for d in ("hike", "cut")}
        if any(pd.isna(v) for v in last.values()) or last["cut"] < last["hike"]:
            continue
        w = y[y["start"].isin(last.values())].pivot_table(index="bank", columns="direction", values="beta")
        gap = (w["hike"] - w["cut"]).dropna()
        if len(gap) < 3:
            continue
        rng = np.random.default_rng(seed)
        boot = gap.to_numpy()[rng.integers(0, len(gap), (n_boot, len(gap)))].mean(axis=1)
        system = b[(b["bank"] == "System") & (b["lag_months"] == lag) & (b["start"].isin(last.values()))]
        sb = system.set_index("direction")["beta"]
        rows.append(
            {
                "lag_months": lag,
                "hike_cycle": f"{last['hike']}",
                "cut_cycle": f"{last['cut']}",
                "system_beta_hike": sb.get("hike", np.nan),
                "system_beta_cut": sb.get("cut", np.nan),
                "banks": len(gap),
                "banks_hike_above_cut": int((gap > 0).sum()),
                "mean_gap": gap.mean(),
                "ci_low": np.percentile(boot, 2.5),
                "ci_high": np.percentile(boot, 97.5),
                "t_p_value": stats.ttest_1samp(gap, 0.0).pvalue,
                # banks share the same rate shock, so the sign count is the cautious read
                "sign_p_value": stats.binomtest(int((gap > 0).sum()), len(gap), 0.5).pvalue,
            }
        )
    return pd.DataFrame(rows)


SPREAD_LAGS = 3  # months of rate moves allowed to reach the cost in `spread_model`
SPREAD_FROM = "2012-04"  # first month with interest split from the UF readjustment


def spread_model(costs: pd.DataFrame, tpm: pd.Series, lags: int = SPREAD_LAGS, start: str = SPREAD_FROM):
    """Error-correction model of the cost of term deposits, by bank and for the system.

        d cost_t = a + sum_k up_k * max(d TPM_{t-k}, 0) + sum_k down_k * min(d TPM_{t-k}, 0)
                   + gamma * (cost - TPM)_{t-1} + rho * d cost_{t-1} + e_t

    `pass_up` and `pass_down` are the sums of the rate coefficients over 0..lags months: the
    share of a 1-point rise (fall) in the TPM that reaches the cost within `lags` months, with
    the pull towards the rate held apart in `gamma` (share of the gap closed each month).
    `diff_p_value` tests pass_up = pass_down with HAC standard errors.
    """
    import statsmodels.api as sm

    rows = []
    for bank, df in costs[costs["term_cost_measure"] == "interest"].groupby("bank"):
        d = pd.DataFrame({"c": df.set_index("period")["term_cost"], "r": tpm}).dropna()
        d = d[d.index >= start]
        if len(d) < 60:
            continue
        dc, dr = d["c"].diff(), d["r"].diff()
        X = pd.DataFrame(index=d.index)
        for k in range(lags + 1):
            X[f"up{k}"] = dr.clip(lower=0).shift(k)
            X[f"dn{k}"] = dr.clip(upper=0).shift(k)
        X["gap"] = (d["c"] - d["r"]).shift(1)
        X["dc1"] = dc.shift(1)
        Z = pd.concat([dc.rename("dc"), X], axis=1).dropna()
        y = Z.pop("dc")
        res = sm.OLS(y, sm.add_constant(Z)).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
        names = list(res.params.index)
        r = np.zeros(len(names))
        for k in range(lags + 1):
            r[names.index(f"up{k}")], r[names.index(f"dn{k}")] = 1.0, -1.0
        test = res.t_test(r)
        up = [f"up{k}" for k in range(lags + 1)]
        dn = [f"dn{k}" for k in range(lags + 1)]
        rows.append(
            {
                "bank": bank,
                "months": int(res.nobs),
                "pass_up": float(res.params[up].sum()),
                "pass_down": float(res.params[dn].sum()),
                "diff": float(np.asarray(test.effect).ravel()[0]),
                "diff_p_value": float(np.asarray(test.pvalue).ravel()[0]),
                "gap_closed_per_month": float(-res.params["gap"]),
                "gap_se": float(res.bse["gap"]),
            }
        )
    return pd.DataFrame(rows)
