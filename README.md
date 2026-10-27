# Customer Cross-Reference

Matches the same customer across SAP, CRM and Billing and gives each real customer one **Golden ID**.
It uses fuzzy matching first, a **local LLM (Ollama)** for borderline pairs, and a review queue for anything uncertain. No data leaves your machine.

For the full flow, inputs, outputs and decision rules, see [PIPELINE.md](PIPELINE.md).

## Quick start

Requires Python 3.10+ and, for the LLM step, [Ollama](https://ollama.com).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# local LLM (skip if you only use --mock)
ollama serve                 # in a separate terminal
ollama pull llama3.2:3b

pytest -q                    # 56 tests, no real LLM or database needed
python run.py                # run on the demo CSVs with the local model
python run.py --mock         # run without any model
```

## What you get

Written to `output/` and `staging/`:

| File | Contents |
|---|---|
| `output/golden.xlsx` | Every record with its `golden_id`, match method, score, reason, timestamp |
| `output/review.xlsx` | Pairs a human must decide |
| `output/rejects.csv` | Junk or profanity rows, and rows or pairs that raised an error |
| `output/run_report.json` | Model used, per-source row counts, summary, database write status |
| `staging/<run id>/` | Raw snapshot of each source plus `manifest.json` |

Exit code `0` means success. Exit code `4` means a required source could not be read.

## Using your own data

**CSV files:** replace `data/sap.csv`, `crm.csv` and `billing.csv`. Columns: `cust_id, name, address, pin`. Or edit `config/connectors.yaml` to point at other files and map their column names.

**Databases (SAP, CRM, Billing):**
1. Copy `config/connectors.sql.example.yaml` to `config/connectors.yaml` and edit the queries and column mapping.
2. Install the driver you need, for example `hdbcli sqlalchemy-hana` (SAP HANA), `psycopg2-binary` (Postgres) or `pymysql` (MySQL).
3. Set the connection URLs as environment variables, never in the config:
   ```bash
   export SAP_DB_URL="hana+hdbcli://USER:PASS@host:30015"
   export CRM_DB_URL="postgresql+psycopg2://USER:PASS@host/db?sslmode=require"
   export BILLING_DB_URL="mysql+pymysql://USER:PASS@host/db"
   ```
4. Use a read-only database user.

The SQL connectors are tested with mocks only. Expect to adjust queries, drivers and network access on first use against real systems.

## Command line

```
python run.py [--config PATH] [--mock] [--since DATE]
```

| Option | Meaning |
|---|---|
| `--config PATH` | Config file (default `config/connectors.yaml`) |
| `--mock` | Use a fake LLM that never confirms a match; no model needed |
| `--since DATE` | Incremental extract for SQL queries containing `:since`; omit for a full refresh |

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `OLLAMA_HOST` | Local LLM server | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `llama3.2:3b` |
| `SAP_DB_URL`, `CRM_DB_URL`, `BILLING_DB_URL` | Source database URLs (names set in config) | none |
| `MDM_DB_URL` | Optional database you own for golden tables. If unset, **nothing is written to any database** | none |

## Safety at a glance

- PII (email, phone, PAN, Aadhaar, GSTIN) is masked before any LLM prompt and never logged.
- Customer text is treated as untrusted: injection patterns skip the LLM, and the model must return validated JSON.
- The LLM cannot override a hard mismatch, and low confidence goes to human review.
- A missing required source stops the run instead of producing a partial result.
- Excel output is protected against formula injection.
- Source tables are never modified.

## Project layout

```
run.py            entry point
connectors/       one connector per system (csv_source, sql, sap, crm, billing)
config/           connectors.yaml (demo), connectors.sql.example.yaml (real databases)
src/              pipeline, staging, llm_client, resilience, export, mdm_writer, logging
src/security/     validate, pii, profanity, llm_guard
tests/            56 tests using a fake LLM and mocked databases
data/             demo CSVs
```

## Known limitations

- No blocking step: all cross-system pairs are compared. Fine for thousands of records, too slow for millions.
- PII detection is regex based, so names written in free text can be missed.
- Thresholds were tuned on dummy data and need re-tuning on real data.
- The profanity list is small and English only.
- A small local model is weaker than a large one, so keep the review queue.
- The output keeps the original name text, so a name that contains an email or phone number is not masked in `golden.xlsx`.
