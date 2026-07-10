# Security and Trust Boundaries

This document describes what the repository does and does not protect. AI-BI is a local portfolio application, not a hardened multi-user execution service.

## Data privacy

The repository provides `data/mock/generate_mock_data.py` for seeded synthetic retail data. It generates sales, waste, weather, membership, and financial examples for local use.

`.gitignore` excludes local SQLite databases and common Excel/CSV exports. This lowers the chance of committing local datasets but is not a substitute for secret scanning, access controls, retention policies, or a review process.

The browser-assisted pipeline reads portal credentials from environment variables, although a missing password can trigger an interactive prompt. Credentials should not be placed in source code or committed configuration files.

## Generated-code execution

`DataAnalysisAgent` executes provider-generated Python with `exec()` in the same Python process as the application. The initial namespace includes:

- loaded DataFrames under `dfs`;
- Pandas and NumPy;
- Plotly Express and graph objects;
- datetime helpers;
- `result` and `fig` output variables.

This is accurately described as a **controlled execution namespace** because the application chooses the initial objects supplied to the code.

It is not a sandbox or security boundary. Python automatically makes built-ins available unless they are explicitly replaced, and generated code runs with the permissions of the Streamlit process. The implementation does not provide:

- operating-system or container isolation;
- filesystem or network denial;
- an import allow-list;
- CPU, memory, or execution-time limits;
- process termination for runaway code;
- multi-tenant separation;
- an approval step before execution.

Consequently, the current code path should only be used with a trusted provider and non-hostile users/data in a local demonstration environment.

## LLM and prompt boundaries

The router uses skill descriptions, conversation excerpts, and a truncated business-context summary to classify requests. Code generation includes table schemas and sample rows. These prompts can disclose the supplied data to the configured provider.

The router validates returned skill names and filters requested table names. Those checks constrain routing output but do not defend the generated-code path from arbitrary Python behavior or all forms of prompt injection.

## Session persistence

Chat sessions are stored locally as JSON by `modules/session_manager.py`. The repository does not add per-user authorization or encryption for those files. Avoid entering credentials, personal data, or other secrets into chat messages.

## Pipeline considerations

The Selenium workflow passes authenticated cookies from a requests session into Chrome. Chrome is started with `--no-sandbox`, which is a browser launch flag and does not make application-level Python execution safer. Running the browser pipeline should be limited to a controlled machine and a portal account with the minimum permissions necessary for report export.

## Appropriate portfolio claims

The repository demonstrates:

- synthetic-data handling;
- environment-based provider and portal configuration;
- validation of router-selected skills and tables;
- deterministic mocked tests for core agent contracts;
- explicit retry and fallback paths.

It does not demonstrate production authentication, authorization, secret management, audit logging, hardened code isolation, compliance controls, vulnerability management, or incident response.

## Hardening path

Before accepting untrusted prompts or exposing the application to multiple users, generated analysis should move to a separately isolated worker with strict resource limits, a restricted data contract, network/filesystem controls, execution deadlines, and auditable request/response handling. Those changes are intentionally outside the current portfolio implementation.
