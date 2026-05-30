# Expense Tracker

A local Plotly Dash app for ingesting, resolving, and analysing personal expense exports from Samsung Notes and CSV files.

## Overview

This project converts raw expense exports into a clean SQLite-backed expense ledger, then exposes:

- a dashboard for spend trends and word-cloud insights
- an ingestion workflow for `.txt` and `.csv` sources
- a conflict-resolution UI for malformed or ambiguous rows
- future support for autofill-based category assignment

## Key Features

- Ingests Samsung Notes `.txt` exports using date header context
- Supports CSV ingestion with flexible header and currency format parsing
- Stores clean expense records in SQLite
- Detects parsing conflicts and manages them through a UI wizard
- Preserves conflict resolution history so re-imports do not re-flag resolved rows

## Getting Started

### Requirements

- Python 3.10+
- `pip`
- Supabase account and project

### Install

```bash
python -m pip install -r requirements.txt
```

### Setup

1. Create a `.env` file in the project root with:
   ```
   DATABASE_URL=postgresql://[user]:[password]@[host]:[port]/[database]
   ADMIN_TOKEN=your_secret_password
   ```

2. Run the app:
   ```bash
   python app.py
   ```

Then open the browser at the local Dash URL shown in the console.

## Database

This app uses PostgreSQL via Supabase for data storage. The schema includes:

- `expenses`: Main expense records
- `conflicts_pending`: Unresolved parsing conflicts
- `conflict_resolutions`: History of resolved conflicts

Tables are created automatically on first run.

## Ingestion

Upload `.txt` or `.csv` files directly in the Ingestion tab. Files are parsed in memory and results go straight to Supabase—no temporary files are created.

Expected format uses date headers and amount-first lines:

```text
1/6
1.25 phone
1.4 toll
2 toll
2/6
1.5 soda cafe
6.5 chicken sandwich
```

- Date headers are `D/M` with no year
- Year is inferred from the filename
- Expense rows are `amount description`
- Blank lines are ignored

### CSV

CSV ingestion supports flexible header names such as:

- `Date`
- `Purchase`
- `Category`
- `Sub-category`
- `Amount`

It also handles currency prefixes like `din670.000` and decimal separators such as `,` or `.`.

## How Ingestion Works

- `.txt` imports are parsed and only rows newer than the latest stored date are ingested
- `.csv` imports are parsed into expense rows and inserted, replacing duplicate rows by date, amount, and description
- malformed rows become conflicts and are surfaced in the conflict tab

## Conflict Resolution

Conflicts are stored in `conflicts_pending` and require manual resolution.

When a conflict is confirmed, the app:

- inserts, updates, or deletes rows in `expenses`
- records the resolved conflict by hash
- prevents the same bad row from reappearing on future imports


## Dependencies

- `dash`
- `dash-bootstrap-components`
- `dash-ag-grid`
- `plotly`
- `wordcloud`
- `python-dotenv`
- `psycopg2-binary`

## License

MIT
