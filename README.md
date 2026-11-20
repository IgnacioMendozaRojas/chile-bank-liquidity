# chile-bank-liquidity

[![CI](https://github.com/IgnacioMendozaRojas/chile-bank-liquidity/actions/workflows/ci.yml/badge.svg)](https://github.com/IgnacioMendozaRojas/chile-bank-liquidity/actions/workflows/ci.yml)
[![Data](https://github.com/IgnacioMendozaRojas/chile-bank-liquidity/actions/workflows/data.yml/badge.svg)](https://github.com/IgnacioMendozaRojas/chile-bank-liquidity/actions/workflows/data.yml)
[![Model](https://github.com/IgnacioMendozaRojas/chile-bank-liquidity/actions/workflows/model.yml/badge.svg)](https://github.com/IgnacioMendozaRojas/chile-bank-liquidity/actions/workflows/model.yml)

**Liquidity risk: deposit stability, stress outflows, deposit forecasting and the cost of funding.** Every Chilean bank's balance sheet and income statement since 2008, from the CMF API, used to answer the questions a liquidity-risk team answers for its own bank: how much of the deposit base is stable, how much could leave under stress, how well balances can be forecast, who provides the funding, and how fast a rate move reaches its cost.

> At Banco Ripley I work on liquidity risk (deposit balance decay, ILAAP projections under Basel III, cash-flow stress tests). This repository applies the same methods to public data for the banking system and the ten largest banks. No bank data, models or parameters are used.

## Results

- **The pandemic surge was not stable money.** Demand deposits peaked 43% above their pre-2020 trend in May 2021 (CLP 29 trillion of excess), helped by the pension-fund withdrawals. The worst 12-month outflow on record came after it, in 2022, when rate hikes pulled money into term deposits: 20% for the system and 21% to 65% by bank.
- **Simple beats complex for forecasting.** Out of sample since 2014, damped seasonal exponential smoothing misses demand deposits by a median 6.9% at 12 months, against 9.1% for SARIMAX with the policy rate and 10.2% for a random walk. No model anticipated 2020-21: errors reach 23-25% in windows that touch it.
- **Funding from mutual funds is concentrated and rate-sensitive.** Mutual funds hold 15% of the term deposits of the banks shown (37% at BICE) and withdrew 63% of their bank deposits in 12 months in 2021-22. At the last move of each cycle banks had passed on the same share of the 2021-22 hikes and the 2023-25 cuts (0.60 and 0.59); three months later the hikes had kept feeding through (0.69) and the cuts had not (0.62). Across 10 banks the gap is +0.06 (95% CI 0.02 to 0.09, 8 of 10 positive), and banks that rely more on funds passed on more of the hikes (correlation 0.45).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/surge-dark.png">
  <img alt="Demand deposits of the Chilean banking system against their 2012-2019 trend: they rose 43% above trend by May 2021 and fell back after 2022" src="docs/figures/surge-light.png">
</picture>

## What this shows

| Task in a liquidity-risk team | Where it is done here |
|---|---|
| Build a clean monthly history from regulatory data | CMF API, both charts of accounts (2008-2021 and 2022+) mapped to one set of items ([`accounts.py`](src/liquidity/accounts.py), [`data.py`](src/liquidity/data.py)) |
| Reconcile against an independent source | Sum of banks vs the CMF system total and vs Banco Central monetary aggregates ([`checks.py`](src/liquidity/checks.py)) |
| Handle mergers in time series | Mergers detected from the data and folded into pro-forma histories (Corpbanca into Itaú, BBVA into Scotiabank, Security into BICE) |
| Calibrate run-off and the stable core of deposits | Worst and 99% outflows at 1, 3 and 12 months, core deposits, decay curves and half-lives, with and without the pandemic ([`deposits.py`](src/liquidity/deposits.py)) |
| Backtest a stress calibration | Outflows calibrated to 2019 and to 2021, checked against what happened next |
| Forecast balances and judge the model honestly | SARIMAX with the policy rate, month effects and event interventions, against exponential smoothing and a random walk, rolling origin ([`forecast.py`](src/liquidity/forecast.py)) |
| Measure funding concentration and its run-off | Mutual-fund deposits by bank from [chile-mutual-funds-analytics](https://github.com/IgnacioMendozaRojas/chile-mutual-funds-analytics), stressed at the funds' observed outflows ([`funding.py`](src/liquidity/funding.py)) |
| Measure the deposit beta | Interest cost of deposits from income statements, rate cycles found in the TPM, beta per cycle and bank ([`cost.py`](src/liquidity/cost.py)) |
| Keep it current without manual work | Monthly workflows download, recompute, redraw the figures and rewrite the table below |

## Latest reading

<!-- latest:start -->
**Latest reading: September 2026.** Banks held CLP 94.5 trillion of demand and CLP 132.2 trillion of term deposits in September 2026; mutual funds held 14% of the term deposits. Deposit costs kept rising after the last hike but barely fell after the last cut (system beta 0.69 for the hikes, 3 months after).

| Indicator | Latest | Month before | Change | Note |
|---|---:|---:|---:|---|
| Demand deposits, all banks | CLP 94.5 tn | CLP 91.5 tn | +3.2% |  |
| Term deposits, all banks | CLP 132.2 tn | CLP 130.7 tn | +1.1% |  |
| Share of term deposits held by mutual funds | 14.1% | 14.6% | -0.5 pp |  |
| Cost of term deposits, all banks | 4.3% | 4.3% | -0.0 pp |  |
| Policy rate (TPM), month end | 4.5% | 4.5% | +0.0 pp |  |

*Updated automatically on 2026-11-20 from the CMF and Banco Central. CLP tn = CLP trillion (10^12). A note gives the month when an indicator lags the others.*
<!-- latest:end -->

## Findings

**1. Deposit stability.** Over 2008-2026, the system kept 79% of its demand deposits and 74% of its term deposits through the worst 12 months on record (the stable core); fitted decay curves give half-lives of about 44 and 38 months. Term deposits ran hardest in 2020-21 (26% in 12 months, during COVID and the withdrawals); demand deposits in 2022 (20%), as rates rose. Taking the pandemic out lowers the 12-month term stress outflow from 26% to 14%, which is why the window is treated as a structural break rather than averaged in.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/outflows-dark.png">
  <img alt="12-month stress outflow of demand deposits by bank, from 20% for the system to 65% at BTG Pactual" src="docs/figures/outflows-light.png">
</picture>

**2. Backtesting the stress calibration.** Calibrated on data up to 2019, the stress outflows covered what happened next in only 39% of term-deposit and 42% of demand-deposit cases (system and banks, three horizons): 2020-22 was outside the history. Recalibrated with data to 2021, they cover every term-deposit case and 85% of total-deposit cases, but still only 42% for demand deposits, whose 2022-23 outflow was the unwinding of the surge itself.

**3. Forecasting.** SARIMAX on log balances with the policy rate, month dummies, a level shift at each pension-fund withdrawal and a pandemic box explains the history: a 1-point rise in the TPM moves system term deposits up 1.2% (standard error 0.5) and the first and third withdrawals raised demand deposits 12% and 10%. As a forecaster it loses to exponential smoothing at every horizon outside the pandemic, so it is kept for explanation and scenarios, not for point forecasts.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/forecast-dark.png">
  <img alt="Median absolute forecast error by horizon: exponential smoothing 6.9% at 12 months, SARIMAX 9.1%, random walk 10.2%" src="docs/figures/forecast-light.png">
</picture>

**4. Who funds the banks.** Mutual funds' deposits are matched to each bank's term deposits. The share ranges from 1% at BancoEstado to 37% at BICE. Across the banks shown it fell from 21% in April 2020 to 6% in February 2022 and is back at 15%. Applying the funds' own worst outflows (25% in a month, 45% in three, 63% in twelve) gives each bank's exposure to a run by this single type of depositor.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/fund-share-dark.png">
  <img alt="Share of each bank's term deposits held by mutual funds, August 2026" src="docs/figures/fund-share-light.png">
</picture>

**5. The cost of funding.** The cost of term deposits is the interest paid over the last three months, annualised, over the average balance, without the UF readjustment (which follows inflation, not the policy rate). Rate cycles are found in the month-end TPM. In the 2021-22 hikes (TPM +10.75 points) the system's cost had risen 0.60 points per point of TPM at the last hike and 0.69 three months later; in the 2023-25 cuts (TPM -6.75 points) it had fallen 0.59 at the last cut and 0.62 three months later. So the asymmetry is not in how much is passed on during a cycle but in what happens after it: hikes keep repricing maturing deposits, cuts stop. Bank by bank, the hike-minus-cut gap is +0.00 at the last move (95% CI -0.03 to +0.03), +0.06 three months later (0.02 to 0.09, t-test p 0.008) and +0.08 six months later (0.04 to 0.11), from a bootstrap that resamples the 10 banks ([`cost_asymmetry.csv`](data/processed/cost_asymmetry.csv)). One caveat: the cuts began before the hikes had fully reached deposit costs (8.3% against a TPM of 11.25%), so part of the gap may be unfinished pass-through. Earlier cuts (2013-14, 2016-17, 2019-20) had betas of 0.49 to 0.66. Eight of the ten banks show the gap; Falabella passed on more of the cuts (0.83) than of the hikes (0.77). BancoEstado, with almost no fund money, passed on the least in both directions (0.49 and 0.42); BICE the most of the hikes (0.83). Fund reliance goes with pass-through on the way up (correlation 0.45) much more than on the way down (0.23).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/cost-dark.png">
  <img alt="Cost of term deposits and the policy rate, 2012-2026: three months after each cycle, beta of 0.69 for the 2021-22 hikes and 0.62 for the 2023-25 cuts; across banks the gap is +0.06, 95% CI 0.02 to 0.09" src="docs/figures/cost-light.png">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/beta-vs-funds-dark.png">
  <img alt="Deposit beta in the 2021-22 hikes against the share of term deposits held by mutual funds, ten banks" src="docs/figures/beta-vs-funds-light.png">
</picture>

## Caveats

- Balance-sheet data are a proxy for liquidity: there is no maturity ladder, no split by depositor type and no LCR inflow and outflow categories in public data.
- BTG Pactual and Consorcio have short, fast-growing deposit histories, so their stress outflows and trends say little.
- Being below the 2012-2019 trend is not a deficit: the trend is an extrapolation of a period of 13% annual growth.
- Banco del Desarrollo (2009) leaves the data without a matched acquirer and is not folded into any bank.
- The beta-funds correlation uses 10 banks: a signal, not an estimate.
- Before 2012 the CMF reports interest and UF readjustment together; betas of those cycles are flagged and not compared with later ones.
- The CMF API allows 10,000 requests a month per key, and a few statements fail on the API every time (for example Banco de Chile, July 2023); those are read from the CMF's monthly text files instead ([`textfiles.py`](src/liquidity/textfiles.py)), which give the same figures.

## Data and automation

- Sources: CMF API (SBIF v3) balance sheets and income statements by bank; Banco Central de Chile (SIETE API) policy rate, Central Bank bond yields and monetary aggregates; mutual-fund holdings from [chile-mutual-funds-analytics](https://github.com/IgnacioMendozaRojas/chile-mutual-funds-analytics). Events and the pandemic window are listed with their sources in [`config/events.yaml`](config/events.yaml).
- [`data.yml`](.github/workflows/data.yml) runs monthly and adds the new month; it resumes where it stopped, re-requests any bank-month that failed, falls back to the CMF's monthly text files when the API keeps failing, and stops at the API's request limit instead of retrying. A normal month uses about 60 of the CMF's 10,000 monthly requests; each run is capped at 3,000.
- [`model.yml`](.github/workflows/model.yml) then recomputes deposits, funding, cost and forecasts, redraws the figures and rewrites `latest.json` and the table above.
- Results are in [`data/processed`](data/processed) as CSV.

## Run it

```bash
pip install -e ".[dev]"
export CMF_API_KEY=...  BCCH_USER=...  BCCH_PASS=...   # only for `liquidity data`
liquidity data        # download new months and run the checks
liquidity deposits    # outflows, stable core, decay, backtests
liquidity funding     # mutual-fund share of term deposits and run-off
liquidity cost        # cost of deposits and deposit betas
liquidity forecast    # rolling-origin evaluation (about 30 minutes)
liquidity build       # figures, latest.json and the README table
pytest && ruff check .
```

MIT licence. Built by [Ignacio Mendoza Rojas](https://www.linkedin.com/in/ignaciomendozarojas/).
