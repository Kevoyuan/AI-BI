"""Tests for local evaluation utilities; no network or API keys required."""
from pathlib import Path

import numpy as np

from evals.forecast_utils import forecast_metrics, moving_average, seasonal_naive
from evals.run_forecast_eval import evaluate_forecast, make_synthetic_series
from evals.run_router_eval import compute_report, load_cases


def test_router_cases_cover_all_skills():
    cases = load_cases(Path("evals/router_cases.yaml"))
    assert len(cases) >= 40
    assert {case["expected_skill"] for case in cases} == {
        "daily_report", "deep_analysis", "visualization", "forecast_alert", "profit_cost"
    }


def test_router_report_accuracy_and_confusion():
    report = compute_report([
        {"expected": "daily_report", "predicted": "daily_report"},
        {"expected": "visualization", "predicted": "deep_analysis"},
    ])
    assert report["accuracy"] == 0.5
    assert report["confusion"][("visualization", "deep_analysis")] == 1
    assert len(report["failures"]) == 1


def test_forecast_metrics():
    metrics = forecast_metrics([10, 20], [12, 18])
    assert metrics["mae"] == 2
    assert np.isclose(metrics["rmse"], 2)
    assert np.isclose(metrics["mape"], 15)


def test_baselines_and_eval_shape():
    values = list(range(1, 15))
    assert seasonal_naive(values, 3) == [8.0, 9.0, 10.0]
    assert moving_average(values, 2) == [11.0, 11.0]
    result = evaluate_forecast(make_synthetic_series(days=70), horizon=7)
    assert set(result) == {"Seasonal naive", "Moving average", "Current ensemble"}
    assert all(set(metrics) == {"mae", "rmse", "mape"} for metrics in result.values())
