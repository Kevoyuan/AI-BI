"""Small, dependency-light helpers for forecast evaluation."""
from typing import Dict, Iterable

import numpy as np


def forecast_metrics(actual: Iterable[float], predicted: Iterable[float]) -> Dict[str, float]:
    actual = np.asarray(list(actual), dtype=float)
    predicted = np.asarray(list(predicted), dtype=float)
    if actual.shape != predicted.shape or actual.size == 0:
        raise ValueError("actual and predicted must be non-empty and the same length")
    errors = predicted - actual
    denominator = np.where(actual == 0, 1.0, np.abs(actual))
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "mape": float(np.mean(np.abs(errors) / denominator) * 100),
    }


def seasonal_naive(values: Iterable[float], horizon: int, season: int = 7) -> list:
    values = list(values)
    if len(values) < season:
        raise ValueError("seasonal naive needs at least one complete season")
    return [float(values[-season + i % season]) for i in range(horizon)]


def moving_average(values: Iterable[float], horizon: int, window: int = 7) -> list:
    values = list(values)
    if not values:
        raise ValueError("moving average needs at least one value")
    return [float(np.mean(values[-window:]))] * horizon
