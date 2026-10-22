"""Deposit forecasts: SARIMAX with the policy rate, month dummies and event interventions.

Model, on the log of the monthly balance:

    ln D_t = beta * TPM_t + sum_m gamma_m * month_m + sum_k delta_k * event_k + u_t,   u_t ~ ARIMA(p, 1, q)

With d = 1 this is a regression of the monthly change on the change in the policy rate,
so beta is the semi-elasticity of deposits to the rate: the % change in the balance for a
1 percentage-point move in the TPM. Events are level shifts at each pension-fund withdrawal
and a box over the pandemic window (from config/events.yaml).

Evaluation is out of sample, rolling the forecast origin every quarter: each model is
re-estimated with data up to the origin and forecasts 1-12 months ahead with the realised
policy rate (a conditional forecast). Benchmarks: random walk and damped-trend seasonal
exponential smoothing. Errors are reported separately for windows that touch the pandemic.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import yaml

from .deposits import CONFIG, pandemic_window

HORIZONS = (1, 3, 6, 12)
ORDERS = [(p, 1, q) for p in (0, 1, 2) for q in (0, 1)]


def monthly_rate(daily: pd.DataFrame, col: str = "tpm") -> pd.Series:
    s = daily[col].dropna()
    s.index = pd.to_datetime(s.index)
    m = s.resample("ME").mean()
    m.index = m.index.to_period("M").astype(str)
    return m


def design(index: pd.Index, tpm: pd.Series) -> pd.DataFrame:
    """Exogenous regressors for the given months."""
    months = pd.PeriodIndex(index, freq="M")
    X = pd.DataFrame(index=index)
    X["tpm"] = tpm.reindex(index).ffill().values
    for m in range(2, 13):
        X[f"m{m:02d}"] = (months.month == m).astype(float)
    events = yaml.safe_load(CONFIG.read_text())["events"]
    for e in events:
        if "pension-fund withdrawal" in e["name"]:
            X[f"withdrawal_{e['month']}"] = (index >= e["month"]).astype(float)
    a, b = pandemic_window()
    X["pandemic"] = ((index >= a) & (index <= b)).astype(float)
    return X


def _fit(y: pd.Series, X: pd.DataFrame, order):
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    keep = X.columns[X.loc[y.index].std() > 0]  # drop regressors with no variation in the sample
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # plain arrays: string month labels are not a forecastable index for statsmodels
        res = SARIMAX(y.values, exog=X.loc[y.index, keep].values, order=order, trend="n").fit(disp=False)
    res.param_names_ = list(res.model.param_names)
    return res, list(keep)


def select_order(y: pd.Series, X: pd.DataFrame):
    best = None
    for order in ORDERS:
        try:
            res, _ = _fit(y, X, order)
        except Exception:  # noqa: BLE001
            continue
        if best is None or res.aic < best[1]:
            best = (order, res.aic)
    return best[0]


def sarimax_forecast(y, X, order, origin: str, steps: int) -> pd.Series:
    train = y[y.index <= origin]
    res, keep = _fit(train, X, order)
    future = [p for p in X.index if p > origin][:steps]
    fc = res.get_forecast(steps=len(future), exog=X.loc[future, keep].values)
    return pd.Series(np.exp(np.asarray(fc.predicted_mean)), index=future)


def ets_forecast(y, origin: str, steps: int) -> pd.Series:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    train = y[y.index <= origin]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = ExponentialSmoothing(
            train.values, trend="add", damped_trend=True, seasonal="add", seasonal_periods=12
        ).fit()
    future = pd.period_range(pd.Period(origin, "M") + 1, periods=steps, freq="M").astype(str)
    return pd.Series(np.exp(res.forecast(steps)), index=future)


def evaluate(
    balance: pd.Series, tpm: pd.Series, first_origin: str = "2014-12", step: int = 3
) -> tuple[pd.DataFrame, dict]:
    """Rolling-origin absolute % errors by model and horizon; and the full-sample fit."""
    y = np.log(balance[balance > 0].dropna())
    X = design(y.index, tpm).dropna()
    y = y.loc[X.index]
    order = select_order(y, X)
    a, b = pandemic_window()
    rows = []
    origins = [p for p in y.index if p >= first_origin][: -max(HORIZONS)][::step]
    for o in origins:
        actual = np.exp(y[y.index > o].iloc[: max(HORIZONS)])
        try:
            fcs = {
                "SARIMAX": sarimax_forecast(y, X, order, o, max(HORIZONS)),
                "ETS": ets_forecast(y, o, max(HORIZONS)),
                "Random walk": pd.Series(np.exp(y[o]), index=actual.index),
            }
        except Exception:  # noqa: BLE001
            continue
        for h in HORIZONS:
            target = actual.index[h - 1]
            touches = (o >= a and o <= b) or (target >= a and target <= b) or (o < a and target > b)
            for model, fc in fcs.items():
                rows.append(
                    {
                        "origin": o,
                        "horizon_months": h,
                        "model": model,
                        "ape": abs(fc[target] / actual[target] - 1),
                        "window": "pandemic" if touches else "normal",
                    }
                )
    res, keep = _fit(y, X, order)
    params = pd.Series(res.params, index=[*keep, *res.param_names_[len(keep) :]])
    se = pd.Series(res.bse, index=params.index)
    fit = {
        "order": str(order),
        "tpm_semi_elasticity": float(params.get("tpm", np.nan)),
        "tpm_se": float(se.get("tpm", np.nan)),
        **{f"{k}_effect": float(np.expm1(params[k])) for k in keep if k.startswith("withdrawal") or k == "pandemic"},
    }
    return pd.DataFrame(rows), fit


def outlook(balance: pd.Series, tpm: pd.Series, order: str, steps: int = 12) -> pd.DataFrame:
    """Forecast from the last month with the policy rate held at its last value, with a 90% band."""
    y = np.log(balance[balance > 0].dropna())
    future = pd.period_range(pd.Period(y.index[-1], "M") + 1, periods=steps, freq="M").astype(str)
    tpm_ext = pd.concat([tpm, pd.Series(tpm.iloc[-1], index=[p for p in future if p not in tpm.index])])
    X = design(y.index.append(pd.Index(future)), tpm_ext)
    res, keep = _fit(y, X, tuple(int(c) for c in order.strip("()").split(",")))
    fc = res.get_forecast(steps=steps, exog=X.loc[future, keep].values)
    ci = np.asarray(fc.conf_int(alpha=0.10))
    return pd.DataFrame(
        {
            "forecast": np.exp(np.asarray(fc.predicted_mean)),
            "low_90": np.exp(ci[:, 0]),
            "high_90": np.exp(ci[:, 1]),
        },
        index=pd.Index(future, name="period"),
    )
