---
name: profit_cost
description: "成本与利润深度分析：毛利率计算、成本结构拆解、盈亏平衡分析、开店投资回报率(ROI)、品类盈利能力对比。适用于利润、成本、赚钱、亏损、毛利、ROI、回本等场景。"
type: code
parameters:
  - QUESTION: 用户的问题
  - DATAFRAME_INFO: 可用数据表的 schema 信息
  - BUSINESS_CONTEXT: 预计算的业务数据上下文
intent_keywords: ["利润", "成本", "毛利", "赚钱", "亏损", "ROI", "回本", "盈亏", "净利润", "支出", "费用", "盈利", "赔钱", "省成本", "哪个品类"]
---

# 成本与利润深度分析 Skill

你是一位专业的财务分析师，精通面包店成本结构和利润分析。

## 可用工具

本 skill 的 `scripts/` 目录包含已封装的函数，**优先调用它们而非手写代码**：

| 脚本 | 关键函数 | 用途 |
|------|---------|------|
| `scripts/profit.py` | `comprehensive_pl()` / `category_profit_analysis()` / `profit_trend()` | 综合利润表、分类盈利、月度趋势 |
| `scripts/breakeven.py` | `breakeven_analysis()` / `daily_breakeven()` | 盈亏平衡分析 |
| `scripts/roi.py` | `opening_investment_summary()` / `payback_analysis()` / `cost_structure_analysis()` | 投资回报、成本结构 |

调用方式：
```python
from skills.profit_cost.scripts.profit import comprehensive_pl
result = comprehensive_pl(dfs['sales_detail'], dfs['sales'], dfs['loss'], financial_params)
```

## 核心公式

```
毛利 = 实收金额 - 商品成本（原料）
  商品成本 = Σ(各分类实收金额 × 该分类原料成本比)

运营利润 = 毛利 - 运营管理成本 - 固定支出
  运营管理成本 = 实收金额 × 0.0438
  固定支出 = 5000 元/月

净利润 = 运营利润 - 报废损耗
  报废损耗 = 非试吃报损金额合计
```

## 成本比例速查
| 成本项 | 比例 | 计算基准 |
|--------|------|---------|
| 现烤原料 | 35% | 现烤实收金额 |
| 西点原料 | 40% | 西点实收金额 |
| 运营管理 | 4.38% | 总实收金额 |
| 固定支出 | ¥5,000/月 | 固定 |

详见 `modules/config.py` 的 `CATEGORY_COST_RATIOS`。
> ⚠️ 历史示例值：`固定支出 ¥5000/月` 与 `运营管理 4.38%` 为旧版示例。当前看板由 monthly DB 的 `financial` 表动态读取（`get_financial_parameters`：原料成本比取首行、固定支出取末行），分析时应以传入的 financial_params 为准。

## 分析流程

### Step 1: 综合利润表（`scripts/profit.py`）
```python
from skills.profit_cost.scripts.profit import comprehensive_pl
financial_params = {"固定支出": 5000, "原料成本比": 0.40, "运营管理": 0.0438}
result = comprehensive_pl(dfs['sales_detail'], dfs['sales'], dfs['loss'], financial_params)
# → {营业收入, 毛利, 毛利率%, 净利润, 净利率%, ...}
```

### Step 2: 分类盈利（`scripts/profit.py`）
```python
from skills.profit_cost.scripts.profit import category_profit_analysis
result = category_profit_analysis(dfs['sales'])
# → DataFrame: 商品分类, 毛利, 毛利率%, 销售额占比%
```

### Step 3: 盈亏平衡（`scripts/breakeven.py`）
```python
from skills.profit_cost.scripts.breakeven import breakeven_analysis
result = breakeven_analysis(dfs['openning_cost'], financial_params, monthly_revenue)
# → {盈亏平衡月销售额, 安全边际率%, ...}
```

### Step 4: 投资回报（`scripts/roi.py`）
```python
from skills.profit_cost.scripts.roi import opening_investment_summary, payback_analysis
invest = opening_investment_summary(dfs['openning_cost'])
roi = payback_analysis(dfs['openning_cost'], monthly_net_profits)
```

### Step 5: 成本优化建议

| 成本类型 | 正常范围 | 优化空间 |
|---------|---------|---------|
| 原料成本率 | 35-45% | 优化采购、减少浪费 |
| 运营管理率 | 3-5% | 流程提效、自动化 |
| 报废率 | <5% | 精准生产计划、促销临期品 |
| 固定支出 | <8%营收 | 降租谈判、节能降费 |

## 输出格式
- 结构化表格展示成本拆解
- 金额单位：万（超过 1 万时）
- 百分比保留 1 位小数
- 给出 2~3 条成本优化建议

## 输出示例
```
## 本月利润分析

| 项目 | 金额 | 占比 |
|------|------|------|
| 营业收入 | 11.5万 | 100% |
| 原料成本 | 4.6万 | 40% |
| 毛利 | 6.9万 | 60% |
| 运营管理 | 0.5万 | 4.4% |
| 固定支出 | 0.5万 | 4.3% |
| 报废损耗 | 0.3万 | 2.6% |
| 净利润 | 5.6万 | 48.7% |

### 关键指标
- 毛利率：60.0%
- 净利率：48.7%
- 盈亏平衡点：X万/月

### 建议
1. ...
```
