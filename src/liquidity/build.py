"""Tables in data/processed -> figures, latest.json and the "Latest reading" block of the README.

Titles are computed from the data, so they stay true when a new month arrives.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .cost import month_end_rate
from .deposits import CONFIG, pandemic_window
from .figstyle import charts

REPO = "chile-bank-liquidity"
SITE = f"github.com/IgnacioMendozaRojas/{REPO}"
SHORT = {
    "System": "System",
    "BANCO BICE": "BICE",
    "BANCO BTG PACTUAL CHILE": "BTG Pactual",
    "BANCO CONSORCIO": "Consorcio",
    "BANCO DE CHILE": "Banco de Chile",
    "BANCO DE CRÉDITO E INVERSIONES": "BCI",
    "BANCO DEL ESTADO DE CHILE": "BancoEstado",
    "BANCO FALABELLA": "Falabella",
    "BANCO SANTANDER-CHILE": "Santander",
    "ITAÚ CHILE": "Itaú",
    "SCOTIABANK CHILE": "Scotiabank",
    "BANCO INTERNACIONAL": "Internacional",
}


def short(name: str) -> str:
    return SHORT.get(name, name.title())


def _month(p: str) -> str:
    return pd.Period(p, "M").strftime("%b %Y")


def _month_name(p: str) -> str:
    return pd.Period(p, "M").strftime("%B %Y")


def _x(index) -> list:
    return [pd.Timestamp(str(p)) for p in index]


def load(out: Path) -> dict[str, pd.DataFrame]:
    names = [
        "deposits_excess_series",
        "deposits_excess",
        "deposits_outflows",
        "forecast_mape_summary",
        "funding_fund_shares",
        "funding_run_off",
        "cost_series",
        "cost_betas",
    ]
    t = {n: pd.read_csv(out / f"{n}.csv", dtype={"code": str, "period": str}) for n in names}
    t["tpm"] = month_end_rate(pd.read_csv(out / "bcch_rates_daily.csv", index_col=0))
    return t


def _system_fund_share(sh: pd.DataFrame) -> pd.Series:
    g = sh.groupby("period")[["fund_deposits", "term_deposits"]].sum()
    return g["fund_deposits"] / g["term_deposits"]


def _latest_beta(b: pd.DataFrame, lag: int = 3) -> pd.DataFrame:
    """Betas of the most recent cycle that can be measured `lag` months after its end, interest only."""
    x = b[(b["lag_months"] == lag) & (b["measure"] == "interest")]
    return x[x["start"] == x["start"].max()]


# ── figures ───────────────────────────────────────────────────────────────
def figures(t: dict[str, pd.DataFrame], figs: Path) -> None:
    import yaml

    events = yaml.safe_load(CONFIG.read_text())["events"]
    a, b = pandemic_window()

    # 1. Hero: pandemic surge in demand deposits against the pre-2020 trend
    ex = t["deposits_excess_series"]
    s = ex[(ex["bank"] == "System") & (ex["deposits"] == "demand")].set_index("period")
    peak = (s["actual"] / s["trend"] - 1).idxmax()
    pct = s.loc[peak, "actual"] / s.loc[peak, "trend"] - 1
    last = s.index[-1]
    source = (
        f"Source: CMF bank balance sheets (all banks, CMF system total), {_month(s.index[0])} to {_month(last)}; "
        f"trend: log-linear fit on 2012-2019. {SITE}"
    )
    for c in charts(
        f"Demand deposits peaked {pct:.0%} above their pre-2020 trend in {_month(peak)}",
        "Demand deposits of the Chilean banking system, actual and pre-2020 trend, CLP trillion",
        source,
    ):
        c.span(pd.Timestamp(a), pd.Timestamp(b) + pd.offsets.MonthEnd(0), "Pandemic, transfers, withdrawals")
        for e in events:
            if "withdrawal" in e["name"]:
                c.ax.axvline(pd.Timestamp(e["month"]), color=c.t["muted"], linewidth=0.8, linestyle=(0, (2, 2)))
        x = _x(s.index)
        c.line(x, (s["trend"] / 1000).values, 1, "2012-19 trend")
        c.line(x, (s["actual"] / 1000).values, 0, "Actual")
        c.note(
            (pd.Timestamp(peak), s.loc[peak, "actual"] / 1000),
            f"+{pct:.0%} vs trend\n(CLP {(s.loc[peak, 'actual'] - s.loc[peak, 'trend']) / 1000:.1f} tn)",
            (-110, 5),
        )
        c.ax.text(
            pd.Timestamp("2020-08"),
            0.06,
            " dashed: pension-fund withdrawals",
            transform=c.ax.get_xaxis_transform(),
            fontsize=8,
            color=c.t["muted"],
        )
        c.ax.set_ylim(bottom=0)
        c.yaxis("CLP trillion")
        c.save(figs, "surge")

    # 2. Stress outflows by bank, 12 months
    o = t["deposits_outflows"]
    o12 = o[(o["horizon_months"] == 12) & (o["deposits"] == "demand")].set_index("bank")["stress_outflow"]
    o12 = o12.rename(index=short).sort_values()
    hi = o12.drop("System").idxmax()
    for c in charts(
        f"Banks lost up to {o12[hi]:.0%} of demand deposits in 12 months; the system {o12['System']:.0%}",
        "12-month stress outflow of demand deposits: worst on record or 99th percentile, whichever is larger",
        "Source: CMF bank balance sheets, pro forma for mergers; ten largest banks by assets. BTG Pactual and "
        f"Consorcio have short, fast-growing deposit histories. {SITE}",
        size=(9, 4.8),
    ):
        c.hbars(list(o12.index), list(o12.values), fmt="{:.0%}", highlight={"System"})
        c.ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        c.fig.subplots_adjust(left=0.16, right=0.92, top=0.8, bottom=0.2)
        c.save(figs, "outflows")

    # 3. Forecast accuracy, out of sample
    m = t["forecast_mape_summary"]
    hz = [1, 3, 6, 12]
    normal = m[(m["deposits"] == "demand") & (m["window"] == "normal")].set_index("model")[[str(h) for h in hz]]
    pand = m[(m["deposits"] == "demand") & (m["window"] == "pandemic")].set_index("model")["12"]
    best = normal["12"].idxmin()
    for c in charts(
        f"{'Exponential smoothing' if best == 'ETS' else best} forecasts demand deposits best: "
        f"{normal.loc[best, '12']:.1%} error at 12 months",
        "Median absolute error, demand deposits, system and ten banks, quarterly origins since 2014, "
        "outside the pandemic",
        f"Every model's 12-month error rises to {pand.min():.0%}-{pand.max():.0%} when the window touches "
        f"2020-21. SARIMAX: policy rate, month dummies, withdrawal and pandemic interventions. {SITE}",
    ):
        for i, model in enumerate(["ETS", "SARIMAX", "Random walk"]):
            c.line(hz, normal.loc[model].values, i, model)
        c.ax.set_xticks(hz, [f"{h} m" for h in hz])
        c.ax.set_ylim(bottom=0)
        c.yaxis("Median absolute error", pct=True)
        c.xlabel("Forecast horizon")
        c.save(figs, "forecast")

    # 4. Dependence on mutual funds
    sh = t["funding_fund_shares"]
    lp = sh["period"].max()
    latest = sh[sh["period"] == lp].assign(bank=lambda d: d["name"].map(short))
    sys_share = _system_fund_share(sh)
    v = latest.set_index("bank")["fund_share_of_term"].sort_values()
    for c in charts(
        f"Mutual funds hold {v.max():.0%} of {v.idxmax()}'s term deposits; {sys_share[lp]:.0%} across these banks",
        f"Term deposits held by Chilean mutual funds as a share of each bank's term deposits, {_month(lp)}",
        "Source: CMF mutual fund portfolios (chile-mutual-funds-analytics) and CMF bank balance sheets. "
        f"Highlighted: above the average of the banks shown. {SITE}",
    ):
        c.hbars(list(v.index), list(v.values), fmt="{:.0%}", highlight=set(v[v > sys_share[lp]].index))
        c.ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
        c.fig.subplots_adjust(left=0.16, right=0.92, top=0.8, bottom=0.2)
        c.save(figs, "fund-share")

    # 5. Cost of term deposits vs the policy rate
    cs = t["cost_series"]
    sc = cs[cs["bank"] == "System"].set_index("period")
    sc = sc[sc["term_cost_measure"] == "interest"]["term_cost"]
    tpm = t["tpm"].reindex(sc.index)
    bt = t["cost_betas"]
    hike = bt[(bt["bank"] == "System") & (bt["lag_months"] == 3) & (bt["direction"] == "hike")]
    hike = hike[hike["measure"] == "interest"].iloc[-1]
    for c in charts(
        f"Banks passed {hike['beta']:.0%} of the {hike['start'][:4]}-{hike['end'][2:4]} rate hikes "
        "on to the cost of term deposits",
        "Interest paid on term deposits, all banks, 3 months annualised, without UF readjustment; policy rate, %",
        f"Source: CMF income statements and balance sheets, Banco Central de Chile; {_month(sc.index[0])} to "
        f"{_month(sc.index[-1])}. Beta: change in cost over change in TPM, 3 months after the cycle. {SITE}",
    ):
        x = _x(sc.index)
        c.line(x, tpm.values, 1, "Policy rate")
        c.line(x, sc.values, 0, "Cost of term deposits")
        c.span(pd.Timestamp(hike["start"]), pd.Timestamp(hike["end"]), "Hiking cycle")
        end3 = str(pd.Period(hike["end"], "M") + 3)
        if end3 in sc.index:
            c.note((pd.Timestamp(end3), sc[end3]), f"beta {hike['beta']:.2f}", (25, -25))
        c.ax.set_ylim(bottom=0)
        c.yaxis("% per year")
        c.save(figs, "cost")

    # 6. Pass-through against dependence on funds
    lb = _latest_beta(bt)
    lb = lb[lb["bank"] != "System"].dropna(subset=["avg_fund_share_of_term"])
    if len(lb) > 2:
        r = lb["beta"].corr(lb["avg_fund_share_of_term"])
        for c in charts(
            f"More reliance on mutual funds, more pass-through of rate hikes (r = {r:.2f})",
            f"Deposit beta, {lb['start'].iloc[0][:4]}-{lb['end'].iloc[0][2:4]} hikes, 3 months after, vs average "
            "share of term deposits held by funds since 2019",
            f"A signal, not an estimate: {len(lb)} banks. Sources: CMF income statements, balance sheets and "
            f"mutual fund portfolios. {SITE}",
        ):
            c.ax.scatter(lb["avg_fund_share_of_term"], lb["beta"], s=36, color=c.color(0), zorder=3)
            placed: list[tuple[float, float]] = []
            for _, row in lb.sort_values("beta").iterrows():
                x0, y0 = row["avg_fund_share_of_term"], row["beta"]
                near = sum(abs(x0 - px) < 0.04 and abs(y0 - py) < 0.02 for px, py in placed)
                placed.append((x0, y0))
                c.ax.annotate(
                    f" {short(row['bank'])}",
                    (x0, y0),
                    xytext=(3, 7 * near),
                    textcoords="offset points",
                    fontsize=8,
                    color=c.t["text"],
                    va="center",
                )
            k = np.polyfit(lb["avg_fund_share_of_term"], lb["beta"], 1)
            xs = np.linspace(lb["avg_fund_share_of_term"].min(), lb["avg_fund_share_of_term"].max(), 2)
            c.ax.plot(xs, np.polyval(k, xs), color=c.t["muted"], linewidth=1, linestyle=(0, (3, 2)))
            c.ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
            c.xlabel("Average share of term deposits held by mutual funds")
            c.yaxis("Deposit beta")
            c.save(figs, "beta-vs-funds")


# ── latest.json and README ────────────────────────────────────────────────
def latest(t: dict[str, pd.DataFrame], updated: dt.date | None = None) -> dict:
    ex = t["deposits_excess_series"]
    dem = ex[(ex["bank"] == "System") & (ex["deposits"] == "demand")].set_index("period")
    term = ex[(ex["bank"] == "System") & (ex["deposits"] == "term")].set_index("period")
    cs = t["cost_series"]
    cost = cs[(cs["bank"] == "System") & (cs["term_cost_measure"] == "interest")].set_index("period")["term_cost"]
    series = {
        "demand_deposits_tn": (dem["actual"] / 1000, "Demand deposits, all banks", "CLP tn", "pct"),
        "term_deposits_tn": (term["actual"] / 1000, "Term deposits, all banks", "CLP tn", "pct"),
        "fund_share_of_term": (
            _system_fund_share(t["funding_fund_shares"]),
            "Share of term deposits held by mutual funds",
            "share",
            "pp",
        ),
        "term_deposit_cost": (cost / 100, "Cost of term deposits, all banks", "share", "pp"),
        "policy_rate": (t["tpm"] / 100, "Policy rate (TPM), month end", "share", "pp"),
    }
    as_of = dem.index[-1]
    metrics = []
    for mid, (col, label, unit, kind) in series.items():
        col = col.dropna()
        col = col[col.index <= as_of]
        value, period = float(col.iloc[-1]), col.index[-1]
        prev = float(col.iloc[-2])
        metrics.append(
            {
                "id": mid,
                "label": label,
                "value": round(value, 4),
                "unit": unit,
                "period": period,
                "previous": round(prev, 4),
                "change": round(value / prev - 1 if kind == "pct" else value - prev, 4),
                "change_type": "relative" if kind == "pct" else "points",
            }
        )
    m = {x["id"]: x for x in metrics}
    bt = t["cost_betas"]
    hike = bt[(bt["bank"] == "System") & (bt["lag_months"] == 3) & (bt["measure"] == "interest")]
    hike = hike[hike["direction"] == "hike"].iloc[-1]
    return {
        "schema": 1,
        "id": "bank-deposit-liquidity",
        "repo": REPO,
        "title": "Deposit stability and funding cost of Chilean banks",
        "question": "How stable are Chilean banks' deposits, how much could leave under stress, and how fast "
        "do rate moves reach their funding cost?",
        "as_of": as_of,
        "frequency": "monthly",
        "updated": str(updated or dt.date.today()),
        "source": "CMF bank balance sheets and income statements; Banco Central de Chile; CMF fund portfolios",
        "headline": (
            f"Banks held CLP {m['demand_deposits_tn']['value']:.1f} trillion of demand and "
            f"CLP {m['term_deposits_tn']['value']:.1f} trillion of term deposits in {_month_name(as_of)}; mutual "
            f"funds held {m['fund_share_of_term']['value']:.0%} of the term deposits, and banks passed "
            f"{hike['beta']:.0%} of the last rate-hiking cycle on to their cost."
        ),
        "metrics": metrics,
        "figure": "docs/figures/surge-light.png",
    }


def _fmt(value: float, unit: str) -> str:
    return f"{value:.1%}" if unit == "share" else f"CLP {value:,.1f} tn"


def _fmt_change(x: dict) -> str:
    c = x["change"]
    return f"{c:+.1%}" if x["change_type"] == "relative" else f"{c * 100:+.1f} pp"


def readme_block(data: dict) -> str:
    rows = []
    for x in data["metrics"]:
        note = f"latest is {_month_name(x['period'])}" if x["period"] != data["as_of"] else ""
        cells = [x["label"], _fmt(x["value"], x["unit"]), _fmt(x["previous"], x["unit"]), _fmt_change(x), note]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(
        [
            f"**Latest reading: {_month_name(data['as_of'])}.** {data['headline']}",
            "",
            "| Indicator | Latest | Month before | Change | Note |",
            "|---|---:|---:|---:|---|",
            *rows,
            "",
            f"*Updated automatically on {data['updated']} from the CMF and Banco Central. CLP tn = CLP trillion "
            "(10^12). A note gives the month when an indicator lags the others.*",
        ]
    )


def write_readme(readme: Path, block: str) -> None:
    text = readme.read_text(encoding="utf-8")
    new = re.sub(
        r"(<!-- latest:start -->\n)(?:.*?\n)?(<!-- latest:end -->)",
        lambda m: m.group(1) + block + "\n" + m.group(2),
        text,
        flags=re.S,
    )
    readme.write_text(new, encoding="utf-8")


def run(out: Path = Path("data/processed"), figs: Path = Path("docs/figures"), readme: Path = Path("README.md")):
    t = load(out)
    figures(t, figs)
    data = latest(t)
    Path("latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if readme.exists():
        write_readme(readme, readme_block(data))
    return data
