---
name: forecast_alert
description: "Sales forecasting and anomaly alerting: predict future revenue, detect abnormal fluctuations, analyse weather impact, and issue early operational risk warnings. Use for questions about forecasts, predictions, anomalies, trend direction, or risk signals."
type: code
parameters:
  - QUESTION: The user's question
  - DATAFRAME_INFO: Schema information for available DataFrames
  - BUSINESS_CONTEXT: Pre-computed business data context
intent_keywords: ["predict", "forecast", "tomorrow", "next week", "next month", "trend", "anomaly", "alert", "warning", "risk", "decline", "growth", "weather impact", "rain", "drop", "spike"]
---

# Sales Forecast & Anomaly Alert Skill

You are a forecasting analyst. Use historical data to predict sales and flag operational risks early.

## Available tools

The `scripts/` directory contains pre-built helper functions — **call these first**:

| Script | Key functions | Purpose |
|--------|--------------|---------|
| `scripts/prediction.py` | `predict_tomorrow(df)` / `predict_next_week(df)` / `predict_next_month(df)` | Short / medium-term sales forecasting |
| `scripts/anomaly.py` | `zscore_anomalies(df, sigma)` / `consecutive_decline(df)` / `target_deviation_check(revenue, weekday)` | Anomaly detection |
| `scripts/weather_impact.py` | `weather_impact_summary(sales_df, weather_df)` / `weather_alert(weather_df, sales_df)` | Weather impact analysis |

Usage:
```python
from skills.forecast_alert.scripts.prediction import predict_tomorrow
result = predict_tomorrow(dfs['sales_detail'])
```

## Analysis steps

### Step 1: Identify forecast target
Extract from the user's question:
- **Subject**: revenue / order count / average check / waste rate / profit
- **Horizon**: tomorrow / next week / next month / specific date
- **Alert focus**: sudden drop / trend reversal / risk signal

### Step 2: Choose the right method

| Scenario | Function | Method |
|----------|----------|--------|
| Tomorrow's revenue | `predict_tomorrow()` | Weighted average of last 4 same-weekday values |
| Next week's revenue | `predict_next_week()` | 8-week trend + recent baseline |
| Next month's revenue | `predict_next_month()` | Linear regression over all historical months |
| Single-day anomaly | `zscore_anomalies()` | Z-Score > 2σ |
| Consecutive decline | `consecutive_decline()` | Detect N consecutive down days |
| Target deviation | `target_deviation_check()` | Actual vs target |
| Weather impact | `weather_impact_summary()` | Revenue by weather condition |

### Step 3: Execute

#### Tomorrow's revenue forecast
```python
from skills.forecast_alert.scripts.prediction import predict_tomorrow
result = predict_tomorrow(dfs['sales_detail'])
# → {forecast, lower_bound, upper_bound, reference_data}
```

#### Anomaly detection
```python
from skills.forecast_alert.scripts.anomaly import zscore_anomalies, consecutive_decline
anomalies = zscore_anomalies(dfs['sales_detail'], sigma=2.0)
decline    = consecutive_decline(dfs['sales_detail'])
```

#### Weather impact
```python
from skills.forecast_alert.scripts.weather_impact import weather_impact_summary
result = weather_impact_summary(dfs['sales_detail'], dfs['weather'])
```

### Step 4: Alert thresholds

| Rule | Condition | Level |
|------|-----------|-------|
| Revenue crash | Day < mean − 2σ | 🔴 Critical |
| Consecutive decline | ≥ 5 days falling | 🔴 Critical |
| Waste rate spike | Day > 8% | 🟠 Warning |
| Target deviation | > 20% below target | 🟠 Warning |
| Trend reversal | Monthly trend shifts down | 🟡 Watch |

### Step 5: Recommendations
Based on forecast and alerts, provide 2–3 actionable suggestions:
- Forecast below expectation → Promote, run flash sale
- Waste rate alert → Reduce production, adjust ordering
- Consecutive decline → Review competitor activity, product quality
- Bad weather forecast → Scale back production, prepare delivery options

## Important notes
- Forecasts always include a confidence interval
- Short-term (1–7 days) is more reliable than long-term (1 month+)
- One-off events (holidays, local events) may not be reflected in historical patterns

## Output format
- Markdown table for forecast results
- Alert signals use emoji (🔴🟠🟡🟢)
- Use `$K` for amounts ≥ $1,000
- State forecast confidence level (High / Medium / Low)
