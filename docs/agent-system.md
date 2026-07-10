# Agent System

The AI Assistant uses a skill registry, an LLM-based router, and two execution paths: contextual text generation and generated-code data analysis.

## Skill structure

Five skills are currently registered:

| Skill | Type | Purpose |
|---|---|---|
| `daily_report` | text | Prepared operational metrics and targets |
| `deep_analysis` | code | Aggregation, comparison, correlation, and waste analysis |
| `visualization` | code | Plotly-oriented chart requests |
| `forecast_alert` | code | Forecast, anomaly, trend, and weather-impact questions |
| `profit_cost` | code | Profit, break-even, cost, and ROI questions |

A skill directory can contain:

```text
skills/<name>/
├── skill.yaml    Name, description, type, and intent keywords
├── prompt.md     Execution guidance
├── SKILL.md      Self-contained skill documentation/prompt content
└── scripts/      Optional deterministic analytical helpers
```

`SkillRegistry` scans these directories and exposes their descriptions to the router. The descriptions therefore act as the routing table presented to the LLM.

## Resolve → Execute → Render

```text
User question
    │
    ▼
RouterAgent.resolve(query, context, history)
    │
    ├─ builds a list of registered skill names, types, and descriptions
    ├─ requests a JSON classification from the configured provider
    ├─ validates the skill name and requested table names
    └─ falls back to daily_report if classification fails
    │
    ▼
Selected skill type
    ├─ text → build system prompt → stream provider response
    └─ code → DataAnalysisAgent.run()
                  ├─ build selected DataFrame schemas and samples
                  ├─ combine schema with skill instructions
                  ├─ ask the provider for Python code
                  ├─ execute code in a controlled namespace
                  ├─ retry once with failure context when needed
                  └─ ask the provider for a short result summary
    │
    ▼
Streamlit renders answer, code, chart, and result table
```

## Router contract

The router asks for:

```json
{
  "skill": "deep_analysis",
  "reason": "The request compares two data segments.",
  "required_tables": ["sales", "weather"]
}
```

It validates the selected skill against the live registry and filters table names through a fixed allow-list. Invalid JSON, provider errors, and unknown skills fall back to the text-based `daily_report` route.

The routing decision is probabilistic when a live LLM is used. The repository tests routing behavior with deterministic mocked provider responses; they do not measure live-model routing accuracy.

## Router evaluation

`evals/router_cases.yaml` contains 40 labelled examples across all five skills. `evals/run_router_eval.py --mode mock` routes each case through `RouterAgent` with a provider that returns the case label. This checks case loading, report generation, per-skill accounting, and confusion output; it intentionally does not measure model quality.

`evals/run_router_eval.py --mode live` uses the configured provider and reports the same metrics against the live LLM. It exits with a clear credential message when the selected provider key is missing. Results depend on the provider, model, prompt, and case set, so they should be treated as a local snapshot rather than a benchmark.

## Text path

`ContextBuilder` computes a Markdown summary from loaded data, including recent revenue, order count, average check, waste, membership recharge, targets, and financial parameters when the relevant columns exist. The daily-report skill prompt and this context become the system prompt for a streaming provider call.

## Code path

`DataAnalysisAgent` gives the provider:

- the selected skill prompt;
- table names, column types, and sample rows;
- recent conversation context;
- the current analytical question;
- on retry, the failed code and its error message.

Generated code may set `result` and/or `fig`. The execution namespace starts with `dfs`, Pandas, NumPy, Plotly Express, Plotly graph objects, and datetime helpers. This is a controlled execution namespace, not process isolation. See [Security](security.md).

## Provider abstraction

`BaseProvider` defines regular generation, chat, and streaming chat methods. The factory currently supports:

- a DeepSeek/OpenAI-compatible provider selected by default;
- Gemini when `LLM_PROVIDER=gemini`.

Provider selection and credentials come from environment variables. Tests replace providers with mocks, so agent contract tests can run without network calls or API keys.

## Error behavior

- Router/provider/parsing failure: use `daily_report` and include the fallback reason.
- Generated-code failure: return the error to the LLM for one repair attempt.
- Final analysis failure: return an error field and a user-facing explanation.
- Summary-generation failure: return a direct string representation of the computed result.

These behaviors handle common failures but do not impose time, memory, or operating-system resource limits.
