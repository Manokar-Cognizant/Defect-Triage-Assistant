# Phased Build Plan

| Phase | Milestone | Done means |
|---|---|---|
| 1 | Local foundation | Seed data loads; defects persist in SQLite. |
| 2 | Triage agents | Similar matches, owner, points, and explanations are produced. |
| 3 | Lifecycle | Valid transitions work; closing cancels reminders. |
| 4 | Live LLM | API-key mode calls OpenAI; outputs are validated; failures are explicit. |
| 5 | Auditability | Every defect has a clickable, chronological activity timeline. |
| 6 | Delivery surfaces | Streamlit UI and FastAPI endpoints run locally. |
| 7 | Verification | Lint, unit tests, coverage, smoke test, and Postman examples pass. |
| 8 | Submission | Required documents and source are zipped below 150 MB. |

## Remaining production work

Replace synthetic data and the local email outbox with approved enterprise connectors,
add authentication/RBAC, move SQLite to a managed database, and add observability.
