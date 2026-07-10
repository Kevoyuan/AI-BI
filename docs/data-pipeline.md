# Data Pipeline

AI-BI has two ways to obtain local data:

1. `data/mock/generate_mock_data.py` creates seeded portfolio/demo data.
2. `data_pipeline.py` models a browser-assisted export and ETL workflow for a POS-like portal.

The checked-in application can be demonstrated entirely with synthetic data. The browser workflow uses a placeholder base URL and requires environment-specific selectors, credentials, Chrome, and source files.

## Synthetic-data path

```text
Fixed random seed
    │
    ├─ simulate daily orders, products, payments, and waste
    ├─ apply weekday and weather demand patterns
    └─ generate membership and financial helper data
    │
    ▼
database/sales_data_YYYYMM.db for the latest three months
```

The generator writes `sales`, `waste`, `weather`, and `memberships` tables and creates local financial/member summary CSV files. Generated databases and exported tabular data are intended to remain outside version control.

## Browser-assisted export path

```text
Environment credentials
    │
    ▼
requests.Session login with retry/backoff
    │
    ▼
convert session cookies for Selenium
    │
    ▼
headless Chrome export workflows
    ├─ line-item sales
    ├─ waste records
    ├─ membership recharge details
    ├─ card statistics
    ├─ member summary text
    └─ order-level sales tickets
    │
    ▼
verify expected downloads → retry missing export workflows once
    │
    ▼
Excel/CSV parsing → column normalization → date adjustment
    │
    ▼
monthly SQLite database
```

## Authentication and browser handoff

`login_session()` posts credentials through `requests.Session` and retries login failures with exponential backoff. `transfer_cookies()` converts successful session cookies into Selenium-compatible dictionaries. A WebDriver then opens the portal domain, installs those cookies, and refreshes the page.

This avoids a second form login, but it depends on the target portal accepting the transferred cookies. Credentials are read from environment variables; a missing password falls back to an interactive prompt.

## Export workflows

Each report type has a dedicated Selenium function because its navigation and controls differ. Date helpers calculate the requested calendar month and remove `readonly` attributes when a portal date field cannot otherwise be filled.

The orchestrator uses a fresh WebDriver for each export while reusing the authenticated requests session. This reduces browser state leakage between report pages. It is sequential, not parallel.

After the first pass, `check_downloads()` checks six expected filenames. `retry_missing_downloads()` maps missing names back to export functions and makes another attempt. Files still absent after that attempt are logged; there is no queue, checkpoint store, or guaranteed recovery.

## Transform and load

`load_excel_data()` provides shared parsing behavior:

- optional datetime parsing;
- optional column renaming;
- optional business-day timestamp adjustment;
- configurable skipped header rows.

`process_data()` assembles sales, waste, membership, financial, weather, and opening-cost DataFrames. `export_to_database()` converts datetime columns to strings and replaces the corresponding SQLite tables in a monthly database.

## Runtime loading

The Streamlit application does not read the raw exports directly. `modules/data_loader.py` discovers available monthly SQLite files and loads the tables needed by dashboards and the AI Assistant. The Assistant concatenates matching tables across available months before building its business context.

## Operational boundaries

- The example portal URL and browser selectors are not a portable connector specification.
- Several browser steps use fixed waits and depend on page behavior.
- Failed exports are logged and retried, but the workflow is not transactional.
- SQLite writes replace tables and are aimed at local analytical use.
- Pipeline behavior is not covered by the current pytest suite.
- No scheduler, secrets manager, lineage system, or data-quality dashboard is included.
