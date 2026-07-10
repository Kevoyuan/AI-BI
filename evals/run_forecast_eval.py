"""Compare the current profit ensemble with simple forecasting baselines."""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from evals.forecast_utils import forecast_metrics, moving_average, seasonal_naive
from modules.prediction import predict_cumulative_profit


def make_synthetic_series(days: int = 140, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = date(2025, 1, 1)
    rows = []
    for i in range(days):
        day = start + timedelta(days=i)
        weekly = [0, 40, 80, 60, 100, 220, 260][day.weekday()]
        trend = i * 1.5
        noise = rng.normal(0, 25)
        rows.append({"date": day, "net_profit": 1000 + trend + weekly + noise})
    return pd.DataFrame(rows)


def evaluate_forecast(data: pd.DataFrame, horizon: int = 7) -> dict:
    if len(data) <= horizon + 7:
        raise ValueError("forecast evaluation needs more than horizon + 7 rows")
    train = data.iloc[:-horizon].copy()
    test = data.iloc[-horizon:]["net_profit"].to_numpy(dtype=float)
    predictions = {
        "Seasonal naive": seasonal_naive(train["net_profit"], horizon),
        "Moving average": moving_average(train["net_profit"], horizon),
        "Current ensemble": predict_cumulative_profit(
            train, horizon=horizon
        )["ensemble_predictions"],
    }
    return {name: forecast_metrics(test, values) for name, values in predictions.items()}


def main() -> int:
    results = evaluate_forecast(make_synthetic_series())
    print("Forecast evaluation on synthetic data (single final holdout, 7 days)")
    print(f"{'Model':<20} {'MAE':>10} {'RMSE':>10} {'MAPE':>10}")
    for name, metrics in results.items():
        print(f"{name:<20} {metrics['mae']:>10.2f} {metrics['rmse']:>10.2f} {metrics['mape']:>9.2f}%")
    print("These results are local evidence, not production monitoring or financial guidance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
