# Forecasting

`modules/prediction.py` forecasts daily net profit with up to three model implementations and combines successful predictions using fixed weights.

## Input and output

`predict_cumulative_profit()` expects a DataFrame containing `date` and `net_profit`. It normalizes dates, drops missing target values, derives an `is_weekend` feature, and forecasts a configurable number of future days.

The result includes future dates, per-model predictions, ensemble predictions, model weights, Prophet metrics when available, and optional backtest output.

## Models

| Model | Implementation | Main features | Default ensemble weight |
|---|---|---|---:|
| Prophet | `prophet` | Weekly/custom seasonality, weekend regressor, multiplicative mode | 0.60 |
| SARIMA | `statsmodels` SARIMAX | `(1,1,1)(1,1,1,7)` seasonal specification | 0.30 |
| XGBoost | `xgboost` | Seven lag values, day of week, weekend flag | 0.10 |

The weights are fixed rules rather than weights learned from backtest performance.

## Forecast flow

```text
date + net_profit history
          │
          ├─ Prophet fit/predict
          ├─ SARIMA fit/predict
          └─ XGBoost lag-feature fit/predict
          │
          ▼
availability-based weight selection
          │
          ▼
weighted daily ensemble forecast
```

## Degradation behavior

Each runner catches import or fitting failures and returns a seven-day historical mean repeated across the requested horizon. `_compute_weights()` then selects weights according to model availability:

| Successful model fits | Prophet | SARIMA | XGBoost |
|---|---:|---:|---:|
| All three | 0.60 | 0.30 | 0.10 |
| Prophet + SARIMA | 0.70 | 0.30 | 0.00 |
| Prophet only | 1.00 | 0.00 | 0.00 |
| SARIMA only | 0.00 | 1.00 | 0.00 |
| Neither Prophet nor SARIMA | 1.00 | 0.00 | 0.00 |

In the final row, the `prophet_predictions` slot contains the moving-average fallback even though Prophet did not fit. Consumers should check the success flags and weights rather than infer model success from the presence of values.

## Evaluation

When enabled and enough rows exist, the function holds out the last `backtest_days` observations and calls `_run_backtest()`. The current implementation can report MSE, MAE, and MAPE for model results it is able to align with the held-out dates.

Prophet also attempts its own cross-validation using a 14-day initial window, a 7-day period, and a 7-day horizon. Failures in that diagnostic step produce `NaN` metrics without discarding an otherwise successful forecast.

### Baseline comparison

`evals/run_forecast_eval.py` creates a seeded synthetic 140-day profit series, holds out the final seven days, and compares:

- seasonal naive: repeat the same weekday from the prior week;
- seven-day moving average;
- current ensemble: `predict_cumulative_profit()` with its existing model availability and weight rules.

The script reports MAE, RMSE, and MAPE. This is a single final holdout, not rolling-origin validation. In the latest local run with seed 42, the current ensemble scored MAE 31.19, RMSE 35.60, and MAPE 2.39%, versus seasonal naive at 40.17 / 50.68 / 3.02% and moving average at 71.55 / 95.59 / 5.16%. This result is a reproducible snapshot on one synthetic series; it does not imply the ensemble will always beat either baseline, generalize to new data, or provide financial forecasting validation. Rerun the script when dependencies or evaluation inputs change.

## Important limitations

- The current pytest suite does not directly test `modules/prediction.py`.
- Ensemble weights are heuristic and are not calibrated from observed error.
- XGBoost future lag rows reuse historical observations rather than recursively incorporating earlier predictions.
- The optional backtest implementation does not currently calculate a combined ensemble score and does not evaluate XGBoost in `_run_backtest()`.
- Prophet date alignment in the holdout path depends on the forecast frame containing the held-out dates.
- A moving-average fallback maintains an output shape but is not evidence of forecast quality.
- No confidence calibration, drift monitoring, model registry, or scheduled retraining is included.

Forecast results should therefore be presented as an exploratory decision-support feature, not as validated financial guidance.

## Separate forecast skill

The `forecast_alert` agent skill also supports natural-language revenue forecast and anomaly questions. Its helper scripts use lightweight statistical/trend routines designed for conversational analysis. That skill path is distinct from the dashboard profit ensemble in `modules/prediction.py`.
