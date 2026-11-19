# AI HR Productivity Hub

[![Python Tests](https://github.com/nguyenvith17/AI_HRDataHub/actions/workflows/main.yml/badge.svg)](https://github.com/nguyenvith17/AI_HRDataHub/actions/workflows/main.yml)

**Recruitment Analytics Pilot · v0.2 · Python / FastAPI / SQLite · Synthetic data only**

A portfolio prototype that transforms fragmented recruitment spreadsheets into validated, auditable recruitment metrics. Based on the author's 5-module product PRD, this repository focuses on **Module 01 (Authentication & Authorization)** and **Module 02 (Recruitment Data Intelligence)**, with minimum activity logging.

> **Scope disclaimer:** Functional local demo, **not full PRD compliance**, not a production HR system, and not safe for public internet deployment. Do not use real applicant data.

## What you can demo

- HR Admin login, logout, expiring sessions, server-side access controls; Employee access to recruitment APIs is denied.
- Synthetic recruitment dataset generation; `.csv` and `.xlsx` upload → preview/validation → explicit import confirmation.
- Recruitment dashboard with demand, hires, offer acceptance, time measures and filters.
- Recruitment funnel, sources, recruiter analysis, dataset history, CSV reporting and two-period comparison API.
- Vietnamese rule-based analytics assistant (not a connected LLM), validation-error CSV, KPI formula **metadata** history, activity logs.

## Screenshots

Screenshots will be added after running the app locally. Suggested captures: login, dashboard, upload validation, funnel/source comparison, and API docs. Do not present mockups as live screenshots.

## Quick start (Windows)

1. Install Python 3.11+ from https://www.python.org/downloads/ and select **Add Python to PATH**.
2. Extract the repository ZIP. Open the project folder in File Explorer; type `cmd` in the address bar.
3. Run:

```cmd
py -m pip install -r requirements-dev.txt
py -m uvicorn app:app --reload
```

4. Open **http://127.0.0.1:8000** (API docs: **http://127.0.0.1:8000/docs**).
5. Demo-only login: `admin` / `DemoAdmin!2026`. Employee demo: `employee` / `DemoEmployee!2026`.
6. As admin, generate synthetic sample data, then explore the dashboard.

**Do not double-click `index.html` to run the app.** The browser UI needs the FastAPI server. The `Failed to fetch` error usually means the backend is not reachable.

For macOS/Linux, replace `py` with `python3`.

## Automated tests

```cmd
py -m pytest -q
```

GitHub Actions runs the same suite on pushes and pull requests. Current test coverage is limited; passing tests do **not** establish full PRD compliance.

## Input tables

| Excel sheet / CSV dataset | Required fields |
|---|---|
| `requests` | `requisition_id`, `position`, `department`, `headcount_requested`, `open_date`, `recruiter_id`, `status` |
| `applications` | `application_id`, `candidate_id`, `requisition_id`, `application_date`, `source` |
| `stages` | `application_id`, `stage_name`, `stage_status`, `stage_date` |
| `offers` | `application_id`, `offer_date`, `offer_status` |
| `costs` | `cost_id`, `cost_date`, `cost_amount`, `cost_category` |

Dates: `YYYY-MM-DD`. File import has additional validation rules and limitations. For detailed PRD coverage, see [PRD traceability](docs/PRD_TRACEABILITY.md).

## KPI interpretation

- **Hires**: unique applications with valid `joining_date` in the selected period.
- **Demand**: requested headcount on requisitions opened in the period.
- **Fulfillment**: cohort-aligned hires / demand, not hires from all requisitions divided by newly opened demand.
- **Time to fill**: requisition-level **proxy**, not vacancy-level.
- **Offer acceptance**: Accepted / (Accepted + Rejected); pending and withdrawn excluded.
- **N/A** for zero denominators; costs and source conversions may have incomplete scope attribution.
- Funnel events are counted by event date and may not be monotonically decreasing across bars.

## Architecture

```text
Browser UI (index.html)
       |
       v
FastAPI (app.py) -- Authentication / RBAC / upload validation / KPI calculations
       |
       v
SQLite (local, ignored by Git) -- Users / sessions / datasets / KPI metadata / logs
```

## Project files

```text
app.py                  FastAPI backend and business logic
index.html              Browser UI
requirements.txt        Runtime dependencies
requirements-dev.txt    Test dependencies
tests/test_pilot.py      Automated pilot tests
.github/workflows/      GitHub Actions CI
docs/                   PRD traceability and GitHub instructions
.gitignore              Prevents committing local data and secrets
.env.example            Optional local configuration example (not auto-loaded)
```

## Known gaps / next steps

Interactive column mapping; complete DQ01–DQ12 coverage; ownership history; vacancy-level time-to-fill; complete 18-KPI execution and formula-version persistence; strict cohort funnel; quality/90-day retention; full Excel/PDF exports; genuine AI integration with allowlisted backend functions; full P01–P14 acceptance/security tests. Formula metadata edits **do not change KPI calculations**.

## Security and licensing

Local demo only. Default credentials are intentionally public for testing; do not deploy this build to the internet or use personal HR records. `.env` and local databases are excluded from version control. No open-source license has been selected yet; repository visibility alone does not grant reuse rights. Choose a license before inviting contributions.

## Portfolio summary

**Problem:** fragmented recruitment spreadsheets, inconsistent metric definitions and limited traceability. **Approach:** explicit validation/import workflow, server-calculated metrics, role-protected APIs and dataset/version metadata. **Outcome:** working local prototype with automated pilot tests; no measured productivity improvement or production security claim.

[GitHub upload instructions (Vietnamese)](docs/GITHUB_UPLOAD_WINDOWS.md)
