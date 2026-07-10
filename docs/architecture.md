# Architecture

AI-BI is a single-process Streamlit application backed by local SQLite files. It is organized around dashboard pages, reusable modules, and Markdown-defined analytical skills. It does not use microservices or a separate API server.

## System context

```text
Synthetic generator or POS exports
              │
              ▼
     Excel/CSV transformation
              │
              ▼
      Monthly SQLite databases
              │
       ┌──────┴─────────┐
       ▼                ▼
Streamlit dashboards   AI Assistant
                       │
                       ├─ RouterAgent
                       ├─ contextual text response
                       └─ generated-code analysis
```

The synthetic generator is sufficient for a local portfolio demonstration. `data_pipeline.py` represents the separate browser-assisted ingestion route for a POS-like system and uses placeholder endpoints and environment-based credentials.

## Repository boundaries

| Area | Responsibility |
|---|---|
| `app.py`, `pages/` | Streamlit page composition and rendering |
| `modules/data_loader.py` | Read and combine monthly SQLite data |
| `modules/context_builder.py` | Convert loaded data and financial parameters into LLM-ready business context |
| `modules/router_agent.py` | Select a registered analytical skill |
| `modules/data_agent.py` | Generate, execute, retry, and summarize data-analysis code |
| `modules/prediction.py` | Profit forecasting and optional evaluation |
| `modules/session_manager.py` | JSON chat-session persistence |
| `skills/` | Skill metadata, prompts, and deterministic helper functions |
| `data_pipeline.py` | Authentication, browser exports, transforms, and SQLite writes |

## AI request path

The current request sequence is:

1. `pages/2_AI_Assistant.py` loads all available monthly tables and builds business context.
2. The page stores the user message in Streamlit session state and constructs a `ChatRequest`.
3. `ChatService.handle_message()` calls `RouterAgent.resolve()` and selects a skill and optional tables.
4. A text skill returns a response stream using the prepared business context.
5. A code skill calls `DataAnalysisAgent.run()` and returns text, generated code, a Plotly figure, and result data.
6. The page renders the `ChatResponse` and persists the conversation through `session_manager`.

## Design decisions

### Local, modular application

The project keeps data access, analytics, and presentation in one Python application. This makes the demo straightforward to run and inspect. It also means process scaling, distributed state, and service-level fault isolation are outside the current scope.

### Skills as editable domain instructions

Each skill includes metadata and prompting guidance. The registry scans skill directories at runtime, so a new valid skill becomes visible to the router without adding another routing branch. Python changes may still be required when a skill needs a new deterministic helper or a new data source.

### Application service boundary

`application/chat_service.py` owns the chat Resolve → Execute workflow and returns UI-agnostic `ChatRequest`/`ChatResponse` data structures. The Streamlit page still owns sidebar interactions, session state, data refresh, and rendering, keeping Streamlit-specific behavior out of the service.

### Graceful degradation

Routing defaults to `daily_report` after provider or parsing failures. Code analysis retries once after an error. Forecast models fall back or have their weights redistributed when model fitting fails. These paths improve local robustness but do not replace production observability or recovery controls.

## Current constraints

- Streamlit session state couples UI lifecycle and chat orchestration.
- SQLite is appropriate for the local demo, not concurrent write-heavy workloads.
- Generated code runs in the application process.
- Tests focus on agent contracts and chat helpers; page, pipeline, and forecasting integration are not directly covered.
- There are no deployment, monitoring, or performance benchmark definitions in this repository.
