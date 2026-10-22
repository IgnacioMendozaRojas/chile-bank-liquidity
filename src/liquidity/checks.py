"""Data checks: system totals against the Banco Central, mergers, gaps."""

from __future__ import annotations

import pandas as pd

AGGREGATES = {
    "999": "System total",
    "900": "System aggregate 900",
    "970": "System aggregate 970",
    "980": "System aggregate 980",
}


def is_bank(code) -> bool:
    """Codes 900 and above are system totals and groupings published with the banks."""
    return int(str(code)) < 900


def banks_only(balances: pd.DataFrame) -> pd.DataFrame:
    return balances[balances["code"].map(is_bank)]


def wide(balances: pd.DataFrame, item: str) -> pd.DataFrame:
    """period x bank code table of one item."""
    return balances[balances["item"] == item].pivot_table(index="period", columns="code", values="clp_bn").sort_index()


def system_total(balances: pd.DataFrame) -> pd.DataFrame:
    """Sum over banks against the CMF's own system total (code 999), item by item."""
    banks = banks_only(balances).groupby(["period", "item"])["clp_bn"].sum().unstack()
    total = balances[balances["code"] == "999"].pivot_table(index="period", columns="item", values="clp_bn")
    return (banks / total - 1).round(4)


def system_vs_bcch(balances: pd.DataFrame, bcch: pd.DataFrame) -> pd.DataFrame:
    """Bank-level sums against the monetary aggregates, level ratio and monthly-change gap."""
    b = banks_only(balances)
    out = pd.DataFrame(
        {
            "cmf_demand": wide(b, "demand_deposits").sum(axis=1),
            "cmf_term": wide(b, "term_deposits").sum(axis=1),
        }
    ).join(bcch, how="inner")
    if "system_checking_accounts" in out:
        out["system_demand_deposits"] = out["system_demand_deposits"] + out["system_checking_accounts"]
    out["ratio_demand"] = out["cmf_demand"] / out["system_demand_deposits"]
    out["ratio_term"] = out["cmf_term"] / out["system_term_deposits"]
    for k in ("demand", "term"):
        cmf = out[f"cmf_{k}"].pct_change()
        bc = out[f"system_{k}_deposits"].pct_change()
        out[f"growth_gap_{k}"] = cmf - bc
    return out


def mergers(balances: pd.DataFrame, tolerance: float = 0.25, min_share: float = 0.02) -> pd.DataFrame:
    """Banks that stop reporting, matched to the bank whose assets jump by about their size.

    A bank leaving at month t (last report t-1) with assets A is matched to the surviving
    bank whose total assets rise most between t-1 and t, if that rise is within
    `tolerance` of A and A is at least `min_share` of the acquirer (smaller exits cannot be
    told apart from ordinary monthly moves). Unmatched exits are kept as such.
    """
    balances = banks_only(balances)
    assets = wide(balances, "total_assets")
    names = balances.drop_duplicates("code", keep="last").set_index("code")["name"]
    periods = list(assets.index)
    rows = []
    for i in range(1, len(periods)):
        prev, cur = periods[i - 1], periods[i]
        gone = assets.columns[assets.loc[prev].notna() & assets.loc[cur].isna()]
        jumps = (assets.loc[cur] - assets.loc[prev]).dropna()
        for code in gone:
            a = assets.loc[prev, code]
            target = jumps.idxmax() if len(jumps) else None
            matched = (
                target is not None
                and abs(jumps[target] - a) <= tolerance * a
                and a >= min_share * assets.loc[prev, target]
            )
            rows.append(
                {
                    "last_report": prev,
                    "code": code,
                    "name": names.get(code, code),
                    "assets_clp_bn": round(float(a), 1),
                    "absorbed_by": target if matched else "",
                    "absorbed_by_name": names.get(target, "") if matched else "",
                    "jump_clp_bn": round(float(jumps[target]), 1) if matched else None,
                }
            )
    return pd.DataFrame(rows)


def pro_forma(balances: pd.DataFrame, merges: pd.DataFrame) -> pd.DataFrame:
    """Re-label each absorbed bank's history with its acquirer's code, so a merger is not an inflow."""
    out = banks_only(balances).copy()
    mapping = dict(
        zip(
            merges.loc[merges["absorbed_by"] != "", "code"],
            merges.loc[merges["absorbed_by"] != "", "absorbed_by"],
            strict=True,
        )
    )
    for _ in range(5):  # follow chains: A -> B -> C
        out["code"] = out["code"].map(lambda c: mapping.get(c, c))
    names = balances.drop_duplicates("code", keep="last").set_index("code")["name"]
    out = out.groupby(["period", "code", "item"], as_index=False)["clp_bn"].sum()
    out["name"] = out["code"].map(names)
    return out[["period", "code", "name", "item", "clp_bn"]]
