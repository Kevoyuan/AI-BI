"""
Profit Prediction Module
Multi-model ensemble forecasting for net profit:
  - Prophet   (weekly seasonality + weekend regressor)
  - SARIMA    (seasonal ARIMA)
  - XGBoost   (lag features + day-of-week)

Ensemble weights default to 60/30/10 (Prophet/SARIMA/XGB).
All models fall back to a 7-day moving average if they fail,
so the app never crashes due to insufficient data.
"""
import logging
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    from prophet import Prophet
    from prophet.diagnostics import cross_validation, performance_metrics
    _PROPHET_OK = True
except ImportError:
    logger.warning("Prophet not available — using moving-average fallback.")
    _PROPHET_OK = False

try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    _SARIMA_OK = True
except ImportError:
    _SARIMA_OK = False

try:
    from xgboost import XGBRegressor
    from sklearn.model_selection import train_test_split
    _XGB_OK = True
except ImportError:
    _XGB_OK = False


# ── Main entry point ──────────────────────────────────────────────────────────

def predict_cumulative_profit(
    daily_summary: pd.DataFrame,
    horizon: int = 7,
    enable_backtest: bool = False,
    backtest_days: int = 30,
) -> dict:
    """
    Forecast net profit for the next `horizon` days using an ensemble
    of Prophet, SARIMA, and XGBoost.

    Args:
        daily_summary:   DataFrame with columns 'date' and 'net_profit'.
        horizon:         Number of days to forecast (default 7).
        enable_backtest: If True, hold out the last `backtest_days` for evaluation.
        backtest_days:   Days to hold out for backtesting.

    Returns:
        dict with keys:
            future_dates, ensemble_predictions, prophet_predictions,
            sarima_predictions, xgb_predictions, model_weights,
            mae, rmse, mape, prophet_success, backtest (if enabled)
    """
    # ── Prepare data ──────────────────────────────────────────────────────────
    df = daily_summary[["date", "net_profit"]].copy()
    df.columns = ["ds", "y"]
    df["ds"] = pd.to_datetime(df["ds"].astype(str).str.split().str[0])
    df["is_weekend"] = df["ds"].dt.dayofweek.apply(lambda d: 1 if d >= 4 else 0)
    df = df.dropna(subset=["y"])

    if enable_backtest and len(df) > backtest_days:
        train = df.iloc[:-backtest_days].copy()
        test  = df.iloc[-backtest_days:].copy()
    else:
        train = df.copy()
        test  = None

    # ── Prophet ───────────────────────────────────────────────────────────────
    prophet_preds, prophet_ok, mae, rmse, mape, model, forecast = (
        _run_prophet(train, horizon)
    )

    # ── SARIMA ────────────────────────────────────────────────────────────────
    sarima_preds, sarima_ok, sarima_result = _run_sarima(train, horizon)

    # ── XGBoost ───────────────────────────────────────────────────────────────
    xgb_preds, xgb_ok, xgb_model = _run_xgb(train, prophet_preds, df)

    # ── Future dates ─────────────────────────────────────────────────────────
    last_date    = df["ds"].iloc[-1]
    future_dates = [last_date + pd.Timedelta(days=i + 1) for i in range(horizon)]

    # ── Ensemble ──────────────────────────────────────────────────────────────
    weights = _compute_weights(prophet_ok, sarima_ok, xgb_ok)
    ensemble = (
        np.array(prophet_preds) * weights["prophet"]
        + np.array(sarima_preds) * weights["sarima"]
        + np.array(xgb_preds)   * weights["xgb"]
    )

    results = {
        "future_dates":         future_dates,
        "future_predictions":   prophet_preds,          # kept for backwards compat
        "prophet_predictions":  prophet_preds,
        "sarima_predictions":   sarima_preds,
        "xgb_predictions":      xgb_preds,
        "ensemble_predictions": ensemble.tolist(),
        "model_weights":        weights,
        "model":                model,
        "df":                   df,
        "forecast":             forecast,
        "daily_summary":        daily_summary,
        "mae":                  mae,
        "rmse":                 rmse,
        "mape":                 mape,
        "prophet_success":      prophet_ok,
    }

    # ── Optional backtest ─────────────────────────────────────────────────────
    if enable_backtest and test is not None:
        results["backtest"] = _run_backtest(
            test, model, forecast, sarima_result, xgb_model, weights
        )

    return results


# ── Model runners ─────────────────────────────────────────────────────────────

def _run_prophet(train: pd.DataFrame, horizon: int):
    """Fit Prophet and return (predictions, success, mae, rmse, mape, model, forecast)."""
    fallback = [float(train["y"].tail(7).mean())] * horizon

    if not _PROPHET_OK:
        empty_fc = pd.DataFrame()
        return fallback, False, np.nan, np.nan, np.nan, None, empty_fc

    try:
        m = Prophet(
            weekly_seasonality=True,
            daily_seasonality=False,
            yearly_seasonality=False,
            seasonality_mode="multiplicative",
            seasonality_prior_scale=15,
        )
        m.add_seasonality("weekly_custom", period=7, fourier_order=5, prior_scale=15.0)
        m.add_regressor("is_weekend")
        m.fit(train)

        future = m.make_future_dataframe(periods=horizon)
        future["is_weekend"] = future["ds"].dt.dayofweek.apply(lambda d: 1 if d >= 4 else 0)
        fc = m.predict(future)

        preds = fc["yhat"].iloc[-horizon:].tolist()

        # Cross-validation metrics
        try:
            cv  = cross_validation(m, initial="14 days", period="7 days", horizon="7 days")
            pm  = performance_metrics(cv)
            mae, rmse, mape = pm["mae"].mean(), pm["rmse"].mean(), pm["mape"].mean()
        except Exception:
            mae = rmse = mape = np.nan

        return preds, True, mae, rmse, mape, m, fc

    except Exception as exc:
        logger.warning("Prophet failed: %s", exc)
        return fallback, False, np.nan, np.nan, np.nan, None, pd.DataFrame()


def _run_sarima(train: pd.DataFrame, horizon: int):
    """Fit SARIMA(1,1,1)(1,1,1,7) and return (predictions, success, result)."""
    fallback = [float(train["y"].tail(7).mean())] * horizon

    if not _SARIMA_OK:
        return fallback, False, None

    try:
        m   = SARIMAX(train["y"], order=(1, 1, 1), seasonal_order=(1, 1, 1, 7))
        res = m.fit(disp=False)
        return res.get_forecast(steps=horizon).predicted_mean.tolist(), True, res
    except Exception as exc:
        logger.warning("SARIMA failed: %s", exc)
        return fallback, False, None


def _run_xgb(train: pd.DataFrame, fallback_preds: list, full_df: pd.DataFrame):
    """Fit XGBoost with lag features and return (predictions, success, model)."""
    fallback = [float(train["y"].tail(7).mean())] * len(fallback_preds)

    if not _XGB_OK:
        return fallback, False, None

    try:
        df_xgb = train.copy()
        for lag in range(1, 8):
            df_xgb[f"lag_{lag}"] = df_xgb["y"].shift(lag)
        df_xgb["dow"] = df_xgb["ds"].dt.dayofweek
        df_xgb = df_xgb.dropna()

        X_tr, _ = train_test_split(df_xgb, test_size=0.2, shuffle=False)
        feature_cols = ["is_weekend"] + [f"lag_{i}" for i in range(1, 8)] + ["dow"]
        model = XGBRegressor(n_estimators=500, learning_rate=0.05)
        model.fit(X_tr[feature_cols], X_tr["y"])

        # Build feature rows for future dates
        last_date  = full_df["ds"].iloc[-1]
        future_fts = []
        for step in range(1, len(fallback_preds) + 1):
            fd = last_date + pd.Timedelta(days=step)
            row = {"is_weekend": 1 if fd.dayofweek >= 4 else 0, "dow": fd.dayofweek}
            for lag in range(1, 8):
                idx = -lag
                row[f"lag_{lag}"] = float(full_df["y"].iloc[idx]) if abs(idx) <= len(full_df) else 0
            future_fts.append(row)

        Xf = pd.DataFrame(future_fts)[feature_cols]
        return model.predict(Xf).tolist(), True, model

    except Exception as exc:
        logger.warning("XGBoost failed: %s", exc)
        return fallback, False, None


def _compute_weights(prophet_ok: bool, sarima_ok: bool, xgb_ok: bool) -> dict:
    """Return ensemble weights based on which models succeeded."""
    if prophet_ok and sarima_ok and xgb_ok:
        return {"prophet": 0.60, "sarima": 0.30, "xgb": 0.10}
    elif prophet_ok and sarima_ok:
        return {"prophet": 0.70, "sarima": 0.30, "xgb": 0.00}
    elif prophet_ok:
        return {"prophet": 1.00, "sarima": 0.00, "xgb": 0.00}
    elif sarima_ok:
        return {"prophet": 0.00, "sarima": 1.00, "xgb": 0.00}
    else:
        return {"prophet": 1.00, "sarima": 0.00, "xgb": 0.00}  # moving average fallback


def _run_backtest(test, model, forecast, sarima_result, xgb_model, weights) -> dict:
    """Evaluate all models against the held-out test set."""
    actual = test["y"].tolist()
    if not actual:
        return {}

    def _mse(pred, act):
        return float(np.mean((np.array(pred) - np.array(act)) ** 2))

    def _mae(pred, act):
        return float(np.mean(np.abs(np.array(pred) - np.array(act))))

    def _mape(pred, act):
        act_arr = np.array(act)
        return float(np.mean(np.abs((np.array(pred) - act_arr) / np.where(act_arr == 0, 1, act_arr))) * 100)

    results: dict = {"actual": actual}

    # Prophet
    if model is not None and not forecast.empty:
        p_preds = forecast[forecast["ds"].isin(test["ds"])]["yhat"].tolist()
        if p_preds:
            results["prophet"] = {"predictions": p_preds,
                                  "mse": _mse(p_preds, actual),
                                  "mae": _mae(p_preds, actual),
                                  "mape": _mape(p_preds, actual)}

    # SARIMA
    if sarima_result is not None:
        try:
            s_preds = sarima_result.get_prediction(
                start=len(test), end=len(test) + len(actual) - 1
            ).predicted_mean.tolist()
            results["sarima"] = {"predictions": s_preds,
                                 "mse": _mse(s_preds, actual),
                                 "mae": _mae(s_preds, actual),
                                 "mape": _mape(s_preds, actual)}
        except Exception:
            pass

    return results
