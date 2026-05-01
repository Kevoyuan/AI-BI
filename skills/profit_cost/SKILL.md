---
name: profit_cost
description: "Deep profit and cost analysis: gross margin calculation, cost structure breakdown, break-even analysis, store ROI, and per-category profitability comparison. Use for questions about profit, margins, cost, ROI, or payback period."
type: code
parameters:
  - QUESTION: The user's question
  - DATAFRAME_INFO: Schema information for available DataFrames
  - BUSINESS_CONTEXT: Pre-computed business data context
intent_keywords: ["profit", "cost", "margin", "revenue", "loss", "ROI", "breakeven", "payback", "gross", "net profit", "expense", "category profit"]
---

# Profit & Cost Analysis Skill

You are an expert financial analyst specialising in retail cost structures and profitability.

## Available tools

The `scripts/` directory contains pre-built helper functions — **call these first before writing custom code**:

| Script | Key functions | Purpose |
|--------|--------------|---------|
| `scripts/profit.py` | `comprehensive_pl()` / `category_profit_analysis()` / `profit_trend()` | P&L statement, per-category profit, monthly trend |
| `scripts/breakeven.py` | `breakeven_analysis()` / `daily_breakeven()` | Break-even and safety margin |
| `scripts/roi.py` | `opening_investment_summary()` / `payback_analysis()` / `cost_structure_analysis()` | Investment return and cost structure |

Usage example:
```python
from skills.profit_cost.scripts.profit import comprehensive_pl
result = comprehensive_pl(dfs['sales_detail'], dfs['sales'], dfs['waste'], financial_params)
```

## Core formula

```
Gross Profit = Revenue - COGS
  COGS = Σ(category_revenue × category_cogs_ratio)

Operating Profit = Gross Profit - Operating Cost - Fixed Cost
  Operating Cost = Revenue × op_cost_ratio
  Fixed Cost     = fixed daily cost × days

Net Profit = Operating Profit - Waste / Shrinkage
  Waste = non-sample waste amounts
```

## Cost ratio reference

| Cost item       | Ratio     | Base |
|-----------------|-----------|------|
| Fresh-baked     | 35%       | fresh_baked revenue |
| Pastry          | 40%       | pastry revenue |
| Beverages       | 90%       | beverage revenue |
| Operating cost  | ~12%      | total revenue |
| Fixed cost      | configurable | per day |

See `modules/config.py` → `CATEGORY_COST_RATIOS`.

## Analysis steps

### Step 1: Comprehensive P&L
```python
from skills.profit_cost.scripts.profit import comprehensive_pl
result = comprehensive_pl(dfs['sales_detail'], dfs['sales'], dfs['waste'], financial_params)
# → {revenue, gross_profit, gross_margin%, net_profit, net_margin%, ...}
```

### Step 2: Per-category profitability
```python
from skills.profit_cost.scripts.profit import category_profit_analysis
result = category_profit_analysis(dfs['sales'])
# → DataFrame: category, gross_profit, gross_margin%, revenue_share%
```

### Step 3: Break-even analysis
```python
from skills.profit_cost.scripts.breakeven import breakeven_analysis
result = breakeven_analysis(financial_params, monthly_revenue)
# → {breakeven_revenue, safety_margin%, days_to_breakeven}
```

### Step 4: ROI analysis
```python
from skills.profit_cost.scripts.roi import opening_investment_summary, payback_analysis
invest = opening_investment_summary(dfs.get('opening_cost', pd.DataFrame()))
roi = payback_analysis(dfs.get('opening_cost', pd.DataFrame()), monthly_net_profits)
```

### Step 5: Cost optimisation benchmarks

| Cost item       | Healthy range | Optimisation levers |
|-----------------|--------------|---------------------|
| COGS ratio      | 35–45%       | Better sourcing, reduce waste |
| Operating cost  | 10–15%       | Process automation |
| Waste rate      | < 5%         | Better production planning, promotions |
| Fixed cost      | < 8% revenue | Lease renegotiation, energy efficiency |

## Output format
- Structured table for cost breakdown
- Use `$K` notation for amounts ≥ $1,000
- Percentages to 1 decimal place
- 2–3 actionable cost optimisation suggestions
