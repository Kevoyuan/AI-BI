
# AI-BI — AI-Powered Business Intelligence Platform

> **Production-grade analytics platform** combining automated web scraping, multi-model ML forecasting, and LLM-driven conversational BI — built with Python, Streamlit, and a modular "Thin Harness, Fat Skills" agent architecture.
>
> 📌 *This is a sanitised portfolio project — all business data is synthetic. The architecture, algorithms, and engineering patterns are the primary showcase.*

---

## ✨ Key Highlights

| Engineering Area | What's Demonstrated |
|---|---|
| **Full-Stack Data Pipeline** | Selenium + requests: cookie-bridged auth → headless Chrome export → Excel ETL → SQLite — production-grade, self-healing |
| **Agent Architecture** | Thin orchestration harness (< 50 LOC) with all domain logic in `skills/*.md` — zero-code skill additions |
| **LLM-Powered Router** | Dynamic intent classification: the LLM reads skill descriptions at runtime and picks the best match — no hard-coded `if/elif` |
| **Code-Gen Data Agent** | LLM writes & executes Python against live DataFrames — schema-injected, sandboxed, with auto-retry on failure |
| **Ensemble ML Forecasting** | Prophet + SARIMA + XGBoost with adaptive weight redistribution and optional walk-forward backtesting |
| **Multi-Provider LLM** | Abstract `BaseProvider` factory — swap DeepSeek / Gemini / any OpenAI-compatible endpoint via env var |
| **Rich Visualisation** | pyecharts (ECharts) + Plotly + Altair: 24-h heatmaps, stacked bar, cumulative trend, investment timeline |
| **Test Infrastructure** | Deterministic `MockProvider` fixtures — agent tests run fast without API keys |

---

## 🏗️ Architecture

```
AI-BI/
├── app.py                     # Main dashboard entry point (KPI, trends, heatmaps)
├── data_pipeline.py           # Automated crawl → ETL → SQLite pipeline (700 LOC)
│
├── pages/
│   ├── 1_Daily_Report.py      # Daily ops dashboard (targets, waste, monthly export)
│   ├── 2_AI_Assistant.py      # Conversational BI — Thin Harness
│   └── 3_Startup_Cost.py      # Investment breakdown & ROI analysis
│
├── modules/                   # Core library (22 modules, ~3K LOC)
│   ├── llm_provider.py        # BaseProvider → DeepSeek / Gemini (factory pattern)
│   ├── router_agent.py        # Skill-based intent resolver (dynamic routing table)
│   ├── data_agent.py          # Code-gen + sandboxed exec + auto-retry
│   ├── skill_loader.py        # Singleton skill registry (auto-scans skills/)
│   ├── context_builder.py     # Live business context assembler (injected into prompts)
│   ├── data_loader.py         # Multi-month SQLite aggregator with data cleaning
│   ├── prediction.py          # Prophet + SARIMA + XGBoost ensemble forecasting
│   ├── visualization.py       # Dashboard chart components (pyecharts + Plotly)
│   ├── business_logic.py      # Waste / membership / payment analysis
│   ├── session_manager.py     # JSON chat session persistence
│   └── ...                    # config, date_utils, ui_components, etc.
│
├── skills/                    # Modular analytical skills (Markdown-defined)
│   ├── daily_report/          # Text-based daily ops Q&A
│   ├── deep_analysis/         # Code-gen: cross-table aggregation & correlation
│   ├── visualization/         # Code-gen: Plotly chart generation
│   ├── forecast_alert/        # Code-gen: forecasting & anomaly alerting
│   └── profit_cost/           # Code-gen: P&L, break-even, ROI analysis
│
├── tests/                     # Agent test suite (MockProvider-based)
│   ├── conftest.py            # MockProvider + sample DataFrames fixtures
│   ├── test_router_agent.py   # Routing accuracy & edge cases
│   ├── test_data_agent.py     # Code-gen, execution, retry logic
│   └── test_ai_chat.py        # Chat flow & streaming
│
├── data/mock/
│   └── generate_mock_data.py  # Seeded synthetic data generator → SQLite
│
└── config.yaml                # Business parameters (costs, targets, weather impact)
```

### Routing & Execution Flow

```
User Question
    │
    ▼
RouterAgent.resolve()            ← reads ALL skill descriptions dynamically
    │                             ← LLM picks best-matching skill (JSON response)
    ▼
skill_type == "text" ?
  ├── YES → ContextBuilder injects live metrics → streaming LLM chat
  └── NO  → DataAnalysisAgent.run()
                ├── _build_schema()    ← column names + sample rows
                ├── _generate_code()   ← LLM writes Python (skill prompt as context)
                ├── _execute_code()    ← sandboxed exec() with safe namespace
                │     └── on error → feed error back → _generate_code() (retry)
                └── _summarise()       ← LLM narrates result in plain language
```

### Data Pipeline Flow

```
requests.Session (fast login)
    │
    ▼
transfer_cookies()  ←  bridges auth to Selenium (avoids double login)
    │
    ▼
headless Chrome (6 export workflows)
    ├── export_sales_flow()       → navigates report page, clicks export
    ├── export_waste_records()    → fills date pickers, triggers download
    ├── export_recharge_details() → handles readonly inputs via JS injection
    ├── export_card_statistics()  → renames downloaded file to known name
    ├── export_member_info()      → scrapes DOM text, saves to file
    └── export_sales_tickets()    → multi-step modal workflow
    │
    ▼
check_downloads() + retry_missing_downloads()   ← self-healing with backoff
    │
    ▼
load_excel_data() → clean_waste_data() → export_to_database()
                                            └── SQLite bulk insert
```

---

## 🧠 Design Decisions

### 1. Thin Harness, Fat Skills

The Streamlit page (`2_AI_Assistant.py`) contains **zero business logic** — it only orchestrates routing and rendering. All domain knowledge lives in `skills/` folders as Markdown files:

```
skills/forecast_alert/
├── skill.yaml          # name, description, type ("code"), intent_keywords
├── prompt.md           # Full LLM system prompt with analysis steps
├── SKILL.md            # Combined metadata + prompt (self-contained)
└── scripts/
    ├── prediction.py   # Deterministic: predict_tomorrow(), predict_next_week()
    ├── anomaly.py      # Z-score detection, consecutive decline check
    └── weather_impact.py  # Revenue × weather condition analysis
```

**Adding a new analytical capability = creating one folder + two files.** The router automatically picks it up — no code changes required.

### 2. LLM Router (Dynamic Intent Classification)

The `RouterAgent` does not use hard-coded `if/elif` logic. Instead, it sends the complete skill registry to the LLM as structured text and asks it to return a JSON classification:

```python
# Routing table IS the skill descriptions — no code to maintain
entries = "\n".join(
    f"- **{name}** (type={s.skill_type}): {s.description}"
    for name, s in skills.items()
)
```

Benefits:
- Routing quality improves as skill descriptions improve (tunable without code).
- New skills are instantly routable from the moment they are created.
- Routing decisions are introspectable via the `reason` field in the response.

### 3. Code-Gen Data Agent (Execute + Auto-Retry)

For complex analytical questions, the `DataAnalysisAgent` asks the LLM to write Python code against live DataFrames:

- **Schema injection**: Column names, dtypes, and sample rows are included in the prompt — dramatically reduces hallucinated column references.
- **Skill-specific prompts**: The agent loads the matching `SKILL.md` as the system prompt, giving the LLM domain-specific coding rules and helper function references.
- **Auto-retry**: On execution error, the error message and failed code are fed back to the LLM for one automatic retry with diagnostic hints.
- **Sandboxed execution**: Code runs in a controlled namespace exposing only `pd`, `np`, `px`, `go`, `datetime` — no filesystem or network access.

### 4. Multi-Provider LLM Abstraction

```python
class BaseProvider(ABC):
    def generate(self, system_prompt, user_prompt, json_mode=False) -> str: ...
    def chat(self, system_prompt, history, message) -> str: ...
    def chat_stream(self, system_prompt, history, message) -> Generator: ...

# Swap backend via environment variable — zero code changes
provider = get_provider()  # reads LLM_PROVIDER env var
```

Implemented providers: `DeepSeekProvider` (OpenAI-compatible, works with Ollama/vLLM) and `GeminiProvider`.

### 5. Test Infrastructure (MockProvider)

Agent tests run deterministically without API keys using a programmable `MockProvider`:

```python
class MockProvider:
    """Pattern-matched responses: match by prefix in system/user prompt."""
    def __init__(self, responses=None, json_responses=None): ...
    def generate(self, system_prompt, user_prompt, json_mode=False): ...
    def chat_stream(self, system_prompt, history, message): ...  # yields chunks
```

---

## 📈 ML Forecasting (Ensemble)

`modules/prediction.py` implements a three-model ensemble with graceful degradation:

| Model | Library | Approach | Default Weight |
|---|---|---|---|
| Prophet | `prophet` | Weekly seasonality + weekend regressor + multiplicative mode | 60% |
| SARIMA | `statsmodels` | SARIMAX(1,1,1)(1,1,1,7) — classical seasonal time-series | 30% |
| XGBoost | `xgboost` | 7-day lag features + day-of-week encoding | 10% |

**Key engineering patterns:**
- If any model fails to fit, weights are **automatically redistributed** to surviving models.
- All models fall back to a **7-day moving average** as the safety net — the app never crashes.
- Optional **walk-forward backtesting** holds out the last N days and computes MSE/MAE/MAPE per model.
- Prophet cross-validation via `cross_validation()` for reliable error estimates.

---

## 📊 Dashboard Pages

### Main Dashboard (`app.py`)
KPI cards, daily P&L summary table, profit formula breakdown, sales trend charts, cumulative revenue, product category analysis, hourly sales heatmaps (24h × date), payment method breakdown, membership analysis, customer behavior segmentation, and ML profit prediction — all auto-refreshed from multi-month SQLite data.

### Daily Report (`pages/1_Daily_Report.py`)
Date picker → single-day deep dive: revenue vs weekday-based targets (achievement rate), TC/AC metrics, category breakdown, waste rate, and a monthly summary table with CSV export.

### AI Assistant (`pages/2_AI_Assistant.py`)
Conversational BI interface — type a question in natural language, the router selects the appropriate skill, and the system either answers from pre-computed metrics or generates + executes Python analysis code with Plotly charts.

### Startup Cost (`pages/3_Startup_Cost.py`)
Investment breakdown dashboard: expenditure detail table, category pie chart (Plotly), sub-category bar chart (Altair), cumulative spending timeline, and ROI summary metrics.

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/AI-BI.git
cd AI-BI

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your LLM API key:
#   DEEPSEEK_API_KEY=sk-...
# OR
#   LLM_PROVIDER=gemini
#   GEMINI_API_KEY=AIza...
```

### 3. Generate mock data

```bash
python data/mock/generate_mock_data.py
# Creates database/sales_data_YYYYMM.db for the last 3 months
```

### 4. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

### 5. Run tests

```bash
pytest tests/ -v
# Agent tests run without API keys using MockProvider
```

---

## 🛡️ Data Privacy

This repository contains **zero real business data**. All data is generated by
`data/mock/generate_mock_data.py` using seeded random distributions.
The `.gitignore` explicitly excludes `database/*.db` and any Excel / CSV data files.

---

## 🔧 Configuration

Edit `config.yaml` to adjust business parameters:

```yaml
financial_params:
  fixed_cost: 1500.0       # Daily fixed cost
  raw_material_ratio: 0.35 # COGS ratio

weather_impact:
  sunny: 1.00
  heavy_rain: 0.45

revenue_targets:
  saturday: { revenue: 15000, orders: 380 }
```

---

## 📦 Tech Stack

| Layer | Technologies |
|---|---|
| **UI Framework** | Streamlit 1.41 |
| **Data Pipeline** | Selenium, requests, headless Chrome |
| **Data Processing** | Pandas, NumPy, SQLite |
| **Visualisation** | pyecharts (ECharts), Plotly, Altair |
| **ML Forecasting** | Prophet, statsmodels (SARIMA), XGBoost, scikit-learn |
| **LLM Integration** | OpenAI SDK (DeepSeek-compatible), google-generativeai (Gemini) |
| **Testing** | pytest, MockProvider fixtures |
| **Configuration** | python-dotenv, PyYAML |

---

## 📐 Codebase Metrics

| Category | Count |
|---|---|
| Total Python LOC | ~6,200 |
| Core modules | 22 files |
| Analytical skills | 5 (with 12 helper scripts) |
| Dashboard pages | 4 |
| Test files | 4 (MockProvider-based) |

---

## 📄 License

MIT — see [LICENSE](LICENSE).
