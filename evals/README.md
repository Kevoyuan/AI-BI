# Local evaluations

These scripts provide small, reproducible evidence for the portfolio project. They are intentionally separate from the Streamlit application and do not change routing or forecasting behavior.

## Router

```bash
PYTHONPATH=. python evals/run_router_eval.py --mode mock
PYTHONPATH=. python evals/run_router_eval.py --mode live
```

The case set has 40 labelled examples, eight per current skill. Mock mode validates the evaluation wiring and report shape by returning each expected label; it must not be described as model accuracy. Live mode calls the configured provider and reports an accuracy snapshot. Missing credentials produce a readable message and a non-zero exit code.

## Forecast

```bash
PYTHONPATH=. python evals/run_forecast_eval.py
```

The forecast script creates seeded synthetic profit data, holds out the final seven days, and compares seasonal naive, seven-day moving average, and the current ensemble using MAE, RMSE, and MAPE. It is a single holdout for transparency, not production monitoring, model selection, or financial advice.
