---
name: visualization
description: "AI 助手出图规范：店主明确要图表（趋势/占比/对比/柱状/饼图）时，AI 输出 ```chart JSON spec 或 ```echarts option，前端用本地 ECharts 渲染成交互式图表（tooltip/缩放/图例）。"
type: code
parameters:
  - QUESTION: 用户的问题
  - BUSINESS_CONTEXT: 预计算的业务数据上下文
intent_keywords: ["画", "图", "图表", "趋势图", "柱状图", "饼图", "可视化", "展示", "走势"]
---

# 可视化图表 Skill（ECharts 版）

AI 助手出图走 **前端渲染**，不依赖后端图表库：AI 在回答里附 fenced code block，
前端 `ai_chart.js` 解析后调用本地 ECharts（`web_dashboard/vendor/echarts.min.js`）渲染，
自带交互（tooltip、dataZoom 缩放、图例切换）。

## 推荐格式：```chart spec

```chart
{"type":"line","title":"本周每日销售额","labels":["周一","周二","周三"],"series":[{"name":"实收金额","values":[12000,15000,13000]}],"unit":"元"}
```

| 字段 | 说明 |
|------|------|
| `type` | `line`(折线) / `bar`(柱状) / `hbar`(横向条形) / `pie`(环形占比) |
| `title` | 图表标题（可选） |
| `labels` | 类别/横轴，长度 1~80 |
| `series` | 1~4 组 `{name, values, color?}`；`values` 长度必须与 `labels` 一致 |
| `unit` | 数值单位（可选，如 元/单） |

规则：
1. 先 `fetch_pospal_data` 拉真实数据再画（必要时 `scope:"full"`），不编造数值
2. 超过 60 个数据点先聚合（按天/按周/按月）
3. `line`/`bar` 最多 2 组 series；`pie`/`hbar` 1 组
4. 画图外仍用文字给出结论与建议

## 高级格式：```echarts（特殊需求）

散点、热力图、双轴等特殊需求，直接给 ECharts option（纯 JSON 数据，**禁止函数**）：

```echarts
{"xAxis":{"type":"category","data":["1","2"]},"yAxis":{"type":"value"},"series":[{"type":"scatter","data":[[0,10],[1,15]]}]}
```

限制：option 必须是合法 JSON 对象，长度 ≤ 20000 字符；`formatter` 等只能用字符串模板。

## 图表选择参考

| 用户意图 | 推荐 type |
|---------|----------|
| 销售/报损走势 | `line`（>14 点自动带缩放） |
| 分类对比/排名 | `bar` / `hbar` |
| 占比（支付/分类/会员） | `pie` |
| 天气×销售、双轴、散点 | `echarts` 高级块 |

## 已废弃

旧的 `scripts/*.py`（基于 plotly 的图表工厂：sales_charts/category_charts/loss_charts/
member_charts/dashboard）不再使用——plotly 依赖未安装，且看板前端已自绘图表。仅作历史参考保留。
