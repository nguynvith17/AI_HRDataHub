# PRD traceability — Recruitment Pilot v0.2

Reference: user-provided Recruitment PRD v2.0 (19 Nov 2026). Statuses below are conservative and are **not** a certification of PRD compliance.

| Requirement | Current implementation | Status |
|---|---|---|
| Module 01: login/logout, session expiry, backend role checks | `app.py` login/session/admin routes | Partial: local-demo authentication; no production hardening |
| Module 01: account status and role management | protected `/api/users` routes | Partial: API-only editing |
| Module 02: Excel/CSV import, preview, explicit confirmation | `/api/upload/preview`, `/api/upload/confirm` | Partial: no interactive column mapping |
| DQ01–DQ12 validation | basic and cross-table checks | Partial: not every subcase/workflow |
| Recruitment dashboard | `/api/analytics`, `index.html` | Partial: cohort/period caveats |
| Recruitment funnel, sources, recruiters | analytics response and UI | Partial: event counts not strict cohorts |
| KPI01–KPI18 and formula versioning | selected KPI logic and metadata versions | Partial: metadata edits do not alter calculations |
| Month/quarter/year reporting | date ranges, comparison API, CSV | Partial: no complete Excel/PDF reporting |
| AI recruitment data assistant | rule-based Vietnamese query | Partial: not an LLM |
| Activity logs | `logs` table and protected endpoint | Partial |
| Automated acceptance tests P01–P14 | `tests/test_pilot.py` | Partial: five pytest tests, not all acceptance criteria |

## Methodological guardrails
- Distinguish candidate vs application; a person can submit multiple applications.
- A hire requires a valid joining date.
- Do not compare hires by joining date against newly opened demand without cohort alignment.
- Never average monthly percentages to calculate quarterly/yearly rates.
- Return N/A for zero denominators; do not impute missing data.
- Do not use the rule-based assistant to claim causal findings.

## Portfolio disclosure
This is a **local, synthetic-data prototype**. It is not an ATS, does not screen or rank candidates, and is not safe for internet-facing production use. Only claim test coverage supported by automated results.
