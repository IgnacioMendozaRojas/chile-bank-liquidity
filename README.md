# chile-bank-liquidity

**Liquidity risk and deposit behaviour of Chilean banks**, from public CMF balance sheets and Banco Central data: how stable each bank's deposits are, how much could leave under stress, and how long liquid assets would last.

Work in progress. Step 2, deposit behaviour, is in place: worst and 99% outflows at 1, 3 and 12 months, the stable core, decay curves with half-lives, and a backtest of pre-2020 estimates against 2020-2026, for the system and the ten largest banks (pro-forma for mergers). Step 1, the data layer: monthly balance sheets of every bank since 2008 from the CMF API, mapped across the 2022 change in the chart of accounts, checked against the Banco Central's monetary aggregates, with mergers detected from the data and folded into pro-forma histories.
