
# AI Business Analytics Dashboard

> An AI-powered, modular analytics platform built with Streamlit, Python, and LLMs.
> This is a **de-identified portfolio project** — all business data has been replaced with
> realistic synthetic data. The architecture, algorithms, and engineering patterns are the
> primary showcase.

---

## ✨ Features

| Feature | Details |
|---|---|
| **Automated Data Pipeline** | Selenium + requests: auth → cookie bridge → headless Chrome export → Excel ETL → SQLite |
| **Modular Data Loader** | Multi-month SQLite databases auto-merged into cross-date DataFrames |
| **Thin Harness, Fat Skills** | Orchestration layer stays < 50 lines; all domain logic lives in `skills/*.md` |
| **LLM Router Agent** | Skill-based intent routing — adding a new skill automatically makes it routable |
| **Code-Gen Data Agent** | LLM generates and executes Python code against live DataFrames, with auto-retry |
| **ML Profit Forecasting** | Ensemble of Prophet + SARIMA + XGBoost with optional walk-forward backtesting |
| **Rich Visualisation** | pyecharts (Echarts) + Plotly charts, 24-h heatmaps, stacked bar analysis |
| **Multi-Provider LLM** | Swappable DeepSeek / Gemini backends via unified `BaseProvider` interface |
| **Session Persistence** | Chat history saved as JSON; sessions resumable after page refresh |

---

## 🏗️ Architecture

```
AI-BI/
├── app.py                     # Streamlit main entry point
├── data_pipeline.py           # Automated crawl → ETL → SQLite pipeline
├── pages/
│   └── 2_AI_Assistant.py      # AI Q&A — Thin Harness
│
├── modules/
│   ├── config.py              # Centralised config & schema registry
│   ├── llm_provider.py        # Multi-provider LLM abstraction (DeepSeek / Gemini)
│   ├── router_agent.py        # Skill-based intent resolver
│   ├── data_agent.py          # Code-gen + execution agent
│   ├── context_builder.py     # Live business context assembler
│   ├── skill_loader.py        # Skill registry (auto-scans skills/)
│   ├── data_loader.py         # Multi-month SQLite data loading
│   ├── analysis.py            # Re-export shim → skills/daily_report
│   ├── prediction.py          # Ensemble ML forecasting
│   ├── visualization.py       # Dashboard chart components
│   ├── business_logic.py      # Waste / membership / payment analysis
│   ├── session_manager.py     # JSON chat session persistence
│   └── ...
│
├── skills/
│   ├── daily_report/
│   │   ├── skill.yaml         # Metadata (name, description, type)
│   │   ├── prompt.md          # LLM system prompt
│   │   └── scripts/
│   │       └── daily_summary.py   # Deterministic daily aggregation
│   ├── deep_analysis/
│   │   ├── skill.yaml
│   │   ├── prompt.md
│   │   └── scripts/trend.py
│   ├── visualization/
│   │   └── skill.yaml + prompt.md
│   └── forecast/
│       └── skill.yaml + prompt.md
│
└── data/mock/
    └── generate_mock_data.py  # Generates demo SQLite databases
```

### Routing flow

```
User Query
    │
    ▼
RouterAgent.resolve()          ← reads ALL skill descriptions dynamically
    │                           ← LLM picks best-matching skill
    ▼
skill_type == "text" ?
  ├── YES → build_system_prompt() + streaming chat
  └── NO  → DataAnalysisAgent.run()
                ├── _build_schema()       ← schema description
                ├── _generate_code()      ← LLM writes Python
                ├── _execute_code()       ← sandboxed exec()
                └── _summarise()          ← LLM narrates result
```

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

---

## 🧠 Design Principles

### Thin Harness, Fat Skills

Inspired by the observation that monolithic AI pages quickly become unmaintainable.
The solution: the Streamlit page (harness) orchestrates, but contains zero business logic.
All domain knowledge lives in `skills/*.md` files.

**Adding a new skill = creating one folder + two files** (`skill.yaml`, `prompt.md`).
The router automatically picks it up — no code changes required.

### LLM Router

Rather than a hard-coded `if/elif` intent classifier, the `RouterAgent` sends the
full skill registry to the LLM and asks it to choose the best match. This means:

- Routing quality improves as skill descriptions improve.
- New skills are automatically routable from the moment they are created.
- The routing logic is introspectable and editable without touching Python code.

### Code-Gen Data Agent

For complex questions, the `DataAnalysisAgent` asks the LLM to write Python code
that runs against the live DataFrames. Key engineering decisions:

- **Schema injection**: column names and sample rows are included in the prompt, drastically
  reducing hallucinated column names.
- **Auto-retry**: on execution error, the error message is fed back to the LLM for one retry.
- **Sandboxed execution**: code runs in a controlled namespace with only safe modules exposed.

### Automated Data Pipeline

`data_pipeline.py` demonstrates a production-grade web scraping and ETL flow:

```
requests.Session (fast login)
    │
    ▼
transfer_cookies()  ←  bridges auth to Selenium (avoids double login)
    │
    ▼
headless Chrome
    ├── export_sales_flow()       → navigates report page, clicks export
    ├── export_waste_records()    → fills date pickers, triggers download
    ├── export_recharge_details() → handles readonly inputs via JS injection
    ├── export_card_statistics()  → renames downloaded file to known name
    ├── export_member_info()      → scrapes DOM text, saves to file
    └── export_sales_tickets()    → multi-step modal workflow
    │
    ▼
check_downloads() + retry_missing_downloads()   ← self-healing
    │
    ▼
load_excel_data() → clean_waste_data() → export_to_database()
                                            └── SQLite bulk insert
```

Key patterns: **singleton config** (INI/YAML/env), **exponential-backoff retry**,
**cookie bridge** (requests → Selenium), **business-hour time adjustment**.

---

## 📈 ML Forecasting

`modules/prediction.py` implements a three-model ensemble:

| Model | Library | Strengths |
|---|---|---|
| Prophet | `prophet` | Weekly seasonality, holiday effects, interpretable |
| SARIMA | `statsmodels` | Classical time-series, good with limited data |
| XGBoost | `xgboost` | Non-linear patterns, lag features, day-of-week |

The ensemble weight defaults to **60 / 30 / 10** (Prophet / SARIMA / XGB).
If any model fails, weights are redistributed automatically.
Optional walk-forward backtesting computes dynamic weights based on MSE.

---

## 🛡️ Data Privacy Note

This repository contains **zero real business data**. All data is generated by
`data/mock/generate_mock_data.py` using seeded random distributions.
The `.gitignore` explicitly excludes `database/*.db` and any Excel / CSV data files.

---

## 🔧 Configuration

Edit `config.yaml` to adjust demo parameters:

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

- **Streamlit 1.41** — UI framework
- **Selenium + requests** — web scraping & automated data export
- **Pandas / NumPy** — data manipulation & ETL
- **pyecharts + Plotly** — visualisations
- **Prophet + SARIMA + XGBoost** — forecasting
- **OpenAI SDK** — DeepSeek / OpenAI-compatible LLM
- **google-generativeai** — Gemini LLM
- **SQLite** — lightweight data store (no database server required)

---

## 📄 License

MIT — see [LICENSE](LICENSE).
