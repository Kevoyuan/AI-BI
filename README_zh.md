# AI-BI — 基于 LangGraph 的对话式零售分析平台

[English](README.md) | [简体中文](README_zh.md)

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph%20ReAct-orange.svg)](https://github.com/langchain-ai/langgraph)
[![ECharts](https://img.shields.io/badge/Visualization-ECharts%205-AA344D.svg)](https://echarts.apache.org/)

**AI-BI** 是一个私有零售经营分析系统的**公开脱敏作品集版本**。原系统最初面向真实烘焙门店经营场景开发并实际部署使用；公开版保留了核心工程架构，包括 POS 数据接入、Dashboard 指标聚合、LangGraph 编排、参数化分析工具、缓存与降级机制，以及 AI 流式响应。

AI-BI 将业务看板与 **LangGraph ReAct Agent** 结合：Agent 可以读取当前经营上下文，在需要更多数据或专项分析时自主调用确定性的 Python 工具，并输出自然语言解释、图表、KPI 卡片、行动清单等结构化结果。

核心设计原则很简单：**让 LLM 负责推理与工具选择，把业务计算留在显式、可测试的 Python 函数中。**

> **项目来源与脱敏说明**
>
> 本仓库由私有实际运营系统抽取并脱敏而来，目的是在不暴露真实商业数据的前提下，让项目架构可以公开检查和复现。公开版不需要真实 POS 凭据即可运行，因为数据层可以自动回退到脱敏预热数据和合成 SQLite 数据集。AI 助手本身需要一个 OpenAI-compatible 模型 API Key，默认配置为 DeepSeek。

### 公开版做了哪些改动？

- 删除真实账号凭据、客户识别信息和门店私有数据。
- 将私有运营数据替换为脱敏预热数据和合成 SQLite Demo 数据。
- 对门店位置、财务参数和部署环境等配置做了泛化处理。
- 保留原系统核心 Dashboard、LangGraph 编排、分析工具、缓存和 POS 接入架构。
- 增加公开说明、可复现安装步骤和无需真实业务数据的 Demo fallback 路径。

---

## 这个项目展示了什么？

- **Agentic AI 编排**：使用 LangGraph `StateGraph`、`ToolNode`、`tools_condition` 和 `MemorySaver`。
- **Tool-grounded analytics**：LLM 不直接生成任意计算代码，而是调用明确、可测试的业务分析工具。
- **零售领域分析能力**：销售预测、天气影响、购物篮分析、分时销售模式、商品 ABC、储值健康度。
- **流式 AI 交互**：通过 Server-Sent Events（SSE）将生成中的回答持续推送到浏览器。
- **结构化 AI 输出**：支持 ECharts 图表、KPI 卡片、方案对比、行动清单、预警和表格。
- **弹性数据访问**：内存缓存、Parquet 缓存、脱敏预热数据和合成 SQLite fallback。
- **自动化测试**：覆盖 Agent 路由、分析工具、缓存行为、后端接口和前端渲染。
- **源自真实运营系统的架构**：将私有零售经营流程中的核心架构安全地抽取为可公开复现的 Showcase。

---

## 系统概览

<p align="center">
  <img src="docs/images/system_architecture.png" alt="AI-BI 系统架构" width="100%" />
</p>

```text
浏览器 Dashboard
  ├── GET /api/dashboard
  └── POST /api/ai/chat (SSE)
             │
             ▼
Python HTTP Server
  ├── Dashboard 指标聚合
  └── LangGraph ReAct Agent
          │
          ├── 当前 Dashboard 上下文
          ├── fetch_pospal_data(...)
          └── run_analysis(...)
                  │
                  ├── forecast
                  ├── weather
                  ├── basket
                  ├── hourly
                  ├── abc
                  └── recharge
             │
             ▼
弹性数据层
  ├── 内存缓存
  ├── Parquet 缓存
  ├── 脱敏预热数据
  └── 合成 SQLite fallback
```

### 核心运行路径

| 层级 | 主要文件 | 职责 |
|---|---|---|
| Web UI | `web_dashboard/` | Dashboard、AI 对话抽屉、Artifact 渲染、ECharts 可视化 |
| HTTP/SSE 服务 | `web_dashboard_server.py` | 静态资源、`/api/dashboard`、`/api/ai/chat`、SSE 流 |
| Agent 编排 | `modules/ai_assistant.py` | LangGraph State、ReAct 循环、Memory、Tool Calling、流式回答 |
| 分析工具 | `modules/analysis_tools.py` | 参数化零售分析入口 |
| BI 聚合 | `modules/dashboard_api.py` | Dashboard 指标与业务数据聚合 |
| 数据访问 | `modules/pospal_live_data.py`, `modules/pospal_*.py` | POS 接入、缓存、配额保护、离线 fallback |
| 天气 | `modules/weather_api.py` | Open-Meteo 接入 |
| 测试 | `tests/` | Python Agent/后端测试与 Node.js 前端回归测试 |

---

## LangGraph Agent 设计

AI 助手使用显式循环图，而不是固定 Prompt Chain：

```text
START
  │
  ▼
answer node
  │
  ├── 无需工具 ───────────────────► END
  │
  └── Tool Call
        │
        ▼
     ToolNode
        │
        ▼
   Observation
        │
        └──────────────────────────► answer node
```

Agent 会先接收压缩后的 Dashboard 经营快照。如果当前上下文已经足够回答，就直接生成结果；如果用户询问其他时间范围或需要更深入的专项分析，则调用对应工具。

### 状态与会话记忆

`MemorySaver` 通过 `thread_id` 管理会话，可支持类似这样的多轮问题：

```text
“上个月哪些商品表现比较弱？”
“那周末呢？”
“基于这个结果，哪些商品可以考虑下架？”
```

会话状态与业务数据检索逻辑分离，使 Tool Layer 更容易测试，也更容易定位问题。

### 为什么使用参数化工具，而不是让 LLM 直接生成 Python？

AI-BI 让模型从明确的工具集合中进行选择，而具体业务计算仍由确定性的 Python 函数执行。

这样有三个直接好处：

1. **可复现**：相同工具参数沿用相同的计算路径。
2. **更安全**：模型不会直接执行任意生成的 Python 代码。
3. **可测试**：业务计算可以独立于 LLM 做单元测试。

---

## 六类零售分析能力

| 能力 | 示例调用 | 输出 |
|---|---|---|
| **销售预测** | `run_analysis(analysis="forecast", horizon="tomorrow")` | 基于近期历史的短期销售预测与置信区间 |
| **天气影响** | `run_analysis(analysis="weather")` | 历史天气与销售关系及相关经营信号 |
| **购物篮分析** | `run_analysis(analysis="basket", target_product="...")` | 共购商品、连带率、多件单占比、Lift |
| **分时销售模式** | `run_analysis(analysis="hourly")` | 各小时营收、订单量、客单价及早中晚高峰 |
| **商品 ABC** | `run_analysis(analysis="abc")` | 基于收入贡献的 A/B/C 分类及滞销候选商品 |
| **储值健康度** | `run_analysis(analysis="recharge")` | 新增充值、储值消费及现金流相关指标 |

这些工具刻意比通用 Code Interpreter 更窄。目标不是让 LLM 随意“写分析代码”，而是把可审核、可测试、可复用的业务计算暴露给 Agent。

---

## 结构化 AI 输出

AI 助手不仅输出文本。前端会解析结构化 fenced blocks，并渲染为原生 UI 组件。

目前支持：

```text
chart       → ECharts 图表
metrics     → KPI 卡片
compare     → 方案/前后对比
checklist   → 行动清单
callout     → 预警 / 建议块
Markdown    → 表格和解释文本
```

示例：

````markdown
```metrics
[
  {"label":"Weekly Net Sales","value":"¥32.5K","change":"+14.2%","trend":"up"},
  {"label":"Loss Ratio","value":"2.1%","change":"-0.8%","trend":"down"}
]
```
````

---

## SSE 流式响应

`POST /api/ai/chat` 返回 `text/event-stream`。LangGraph 使用 `stream_mode="messages"`，生成的 `AIMessageChunk` 会持续转发给浏览器。

```text
用户问题
   │
   ▼
LangGraph Agent
   │
   ├── 可选 Tool Call
   │
   ▼
AIMessageChunk Stream
   │
   ▼
SSE Endpoint
   │
   ▼
浏览器逐步渲染回答
```

这里使用 SSE，是因为生成过程中主要需要服务器单向向浏览器推送内容，并不需要 WebSocket 那种双向实时通信。

---

## 数据弹性与 Demo 模式

公开版可以在没有真实 POS 凭据的情况下沿以下路径降级运行：

```text
L1  内存运行时缓存
 ↓
L2  本地 Parquet 缓存
 ↓
L3  脱敏离线预热数据
 ↓
L4  合成 SQLite 数据
```

真实数据链路仍保留了原运营系统中的可配置缓存 TTL 和配额保护逻辑，避免重复 Dashboard 请求不必要地持续访问外部 POS 数据源。

天气数据来自 Open-Meteo，无需 API Key。

---

## 快速开始

### 环境要求

- Python 3.11+
- 若需要使用 AI 助手，需要 OpenAI-compatible 模型 API Key
- 公开 Demo 不强制要求 POS 凭据

### 安装

```bash
git clone https://github.com/Kevoyuan/AI-BI.git
cd AI-BI

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

启用 AI 助手至少需要设置：

```env
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### 启动

```bash
python3 web_dashboard_server.py --host 127.0.0.1 --port 8600
```

浏览器打开：

```text
http://127.0.0.1:8600
```

Unix-like 环境也可以使用：

```bash
bash start_dashboard.sh
```

### 可选：重新生成合成 Demo 数据

```bash
python3 data/mock/generate_mock_data.py
```

---

## 测试

Python 测试覆盖 LangGraph Assistant、分析工具、Dashboard API、缓存、POS Adapter 和天气相关逻辑：

```bash
PYTHONPATH=. pytest -v
```

前端回归测试使用 Node 内置 Test Runner：

```bash
node --test tests/*.test.mjs
node tests/dashboard_render.mjs
```

README 不再硬编码测试数量 Badge，避免测试集扩展后文档中的数字过时。

---

## 仓库结构

```text
AI-BI/
├── api/
│   └── index.py                  # 带认证的 Vercel-compatible 入口
├── data/
│   └── mock/                     # 合成 Demo 数据生成器
├── database/                     # 本地 SQLite Demo 数据
├── docs/
│   └── images/                   # 架构图与产品图
├── modules/
│   ├── ai_assistant.py           # LangGraph ReAct Agent 与流式回答
│   ├── analysis_tools.py         # 参数化分析工具
│   ├── dashboard_api.py          # BI 聚合层
│   ├── pospal_live_data.py       # Live/cache/fallback 数据访问
│   ├── pospal_openapi.py         # POS OpenAPI 接入
│   ├── pospal_webapi.py          # POS Web 接入
│   ├── pospal_quota.py           # 配额保护
│   ├── database.py               # SQLite Helper
│   └── weather_api.py            # Open-Meteo 接入
├── prewarmed_cache/              # 脱敏离线预热数据
├── skills/                       # 领域分析脚本与参考逻辑
├── tests/                        # Python + Node.js 测试
├── web_dashboard/                # HTML/CSS/JS Dashboard 与 Artifact Renderer
├── web_dashboard_server.py       # HTTP API 与 SSE Server
├── start_dashboard.sh            # 启动脚本
├── requirements.txt
└── .env.example
```

---

## 公开 Showcase 的范围与限制

AI-BI 是一个**私有已部署运营系统的公开脱敏版本**。这一点很重要：公开仓库展示的是实际使用过的核心架构和工作流模式，但其中的数据集、配置以及运行环境已经为公开展示和可复现性进行了调整。

当前公开版边界包括：

- Agent 从受控的领域工具集合中选择，而不是运行时任意生成分析代码。
- `MemorySaver` 在公开实现中提供进程内会话状态，并不是分布式持久化方案。
- 本地服务使用 Python `ThreadingHTTPServer`，保持轻量，并非完整生产 Web Framework。
- 合成数据与预热数据用于复现真实数据形态和工作流，但不会暴露私有运营数据。
- 组织级权限控制、分布式状态、集中式可观测性和横向扩展不属于这个公开 Showcase 的范围。

因此，这个公开仓库重点展示最适合公开检查的部分：**Agent 编排、Grounded Analytics、零售数据工作流、可靠性机制、缓存/降级设计，以及端到端的用户侧 AI 体验。**
