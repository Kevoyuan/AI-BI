# AI-BI — Conversational Business Intelligence Portfolio

AI-BI is a Streamlit portfolio project that turns synthetic retail data into dashboards, natural-language analysis, and multi-model profit forecasts.

> All included business data is synthetic. The project demonstrates implementation patterns and trade-offs, not a deployed commercial system.

## What it demonstrates

- **Conversational analytics:** an LLM router selects a Markdown-defined skill, then answers from prepared context or generates a Pandas/Plotly analysis.
- **Data-to-dashboard workflow:** browser-assisted exports and Excel/CSV transforms feed monthly SQLite databases used by four Streamlit pages.
- **Forecasting with graceful degradation:** Prophet, SARIMA, and XGBoost predictions are combined when available, with a moving-average fallback.

## End-to-end example

> **Query:** “Compare revenue on rainy vs sunny days and plot the result.”

```text
Streamlit chat
  → RouterAgent selects deep_analysis or visualization
  → DataAnalysisAgent receives table schemas and skill instructions
  → generated Pandas/Plotly code runs in a controlled execution namespace
  → the page renders a written answer, chart, result data, and generated code
```

The execution namespace is controlled by pre-populating the objects available to generated code. It is **not** an operating-system sandbox and should not be treated as a security boundary. See [Security](docs/security.md).

## Architecture overview

```text
Data sources → export/ETL → monthly SQLite files → loaders/context
                                                    │
User query → Streamlit UI → RouterAgent → selected skill
                                      ├─ text → contextual LLM response
                                      └─ code → DataAnalysisAgent → answer/chart/data

Historical profit → Prophet + SARIMA + XGBoost → weighted forecast
```

The AI Assistant page coordinates Streamlit UI, session/data loading, and rendering. Its chat Resolve → Execute workflow is delegated to `application/chat_service.py`, while routing and analysis remain in reusable agents.

Detailed design notes:

- [Architecture](docs/architecture.md)
- [Agent system](docs/agent-system.md)
- [Data pipeline](docs/data-pipeline.md)
- [Forecasting](docs/forecasting.md)
- [Security and trust boundaries](docs/security.md)

## Quick Start

### 1. Install

```bash
git clone https://github.com/Kevoyuan/AI-BI.git
cd AI-BI
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure an LLM provider

```bash
# Create .env, then set DEEPSEEK_API_KEY.
# Or set LLM_PROVIDER=gemini and provide GEMINI_API_KEY.
```

The repository does not currently include an `.env.example`; keep the local `.env` file outside version control.

### 3. Generate synthetic data

```bash
python data/mock/generate_mock_data.py
```

This creates seeded SQLite data for the latest three calendar months under `database/`.

### 4. Run

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

### 5. Test

```bash
pytest
```

Agent tests use mocked LLM providers and do not require an API key.

## Evidence / Metrics

These figures are repository-level evidence, not runtime or production claims:

| Evidence | Current repository |
|---|---:|
| Streamlit pages | 4, including `app.py` |
| Markdown-defined analytical skills | 5 |
| Agent/chat test cases | 30 |
| Test files | 4 |
| Python source size | ~6.8K lines |
| Forecast implementations | Prophet, SARIMA, XGBoost + moving-average fallback |

Not currently demonstrated by this repository: deployment infrastructure, user authentication, process isolation for generated code, production monitoring, or load/performance benchmarks.

## Project map

```text
app.py                       Main operations dashboard
pages/                       Daily report, AI Assistant, startup cost
modules/                     Data, agents, forecasting, charts, sessions
skills/                      YAML/Markdown skill definitions and helpers
data_pipeline.py             Browser export and SQLite ETL workflow
data/mock/                   Seeded synthetic data generator
tests/                       Router, data-agent, and chat contracts
docs/                        Architecture and implementation notes
```

## Main pages

- **Operations dashboard:** KPIs, profit summary, trends, product mix, hourly activity, payments, and membership views.
- **Daily report:** date-specific revenue, targets, order metrics, category mix, waste, and CSV export.
- **AI Assistant:** routed natural-language questions with text or generated-code analysis paths.
- **Startup cost:** investment breakdown, cumulative spending, and ROI summary.

## Technology

Python, Streamlit, Pandas, NumPy, SQLite, Selenium, Plotly, Altair, pyecharts, Prophet, statsmodels, XGBoost, pytest, DeepSeek-compatible APIs, and Gemini.

## Configuration and data

Business targets and weather factors are configurable in `config.yaml`. Synthetic demo data is produced with a fixed random seed; local databases and tabular exports are excluded through `.gitignore`.

## License

No license file is currently included. Add one before publishing or accepting external contributions.
