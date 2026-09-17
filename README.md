# Defect Triage Assistant Agent

A local hackathon MVP that analyzes production defects, finds likely known errors and
historical matches, recommends an owning team and story-point estimate, and manages
follow-up reminders until the defect is closed.

The application uses only synthetic data. It does not connect to Jira, ServiceNow,
Azure DevOps, email, or messaging systems.

## Features

- Explainable TF-IDF and character n-gram similarity ranking
- Known-error and likely-duplicate detection
- Similarity-weighted owning-team recommendation
- Historical story-point recommendation on the `1, 2, 3, 5, 8, 13` scale
- Recommendation confidence and supporting evidence
- Agent-activity view for intake, similarity, ownership, estimation, reminders, and lifecycle
- User overrides for team and estimate
- Defect lifecycle and status history
- Recurring in-app follow-up reminders
- Automatic reminder cancellation when a defect is closed
- Synthetic known-error and closed-defect knowledge base
- Persistent local SQLite storage

## Run locally

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

Streamlit will display the local URL, normally `http://localhost:8501`.

The application creates `data/defect_triage.db` on first startup and seeds it from
`data/seed.json`. The generated database is intentionally ignored by Git.

## Suggested demo

1. Open **New defect** and select **Load demo defect**.
2. Select the **Demo** reminder profile and choose **Analyze and create defect**.
3. Review the known-error match, similar closed tickets, owner, story points, and rationale.
4. Open **Agent activity** to inspect every specialist stage's evidence and output.
5. Open **Reminders** and choose **Make next reminder due now**.
6. Open **Defect tracker** and move the defect through its lifecycle.
7. Close it, return to **Reminders**, and show that its schedule and due reminders are cancelled.

## Tests and code quality

```powershell
python -m pip install -r requirements-dev.txt
ruff check .
python -m unittest discover -s tests -v
python -m defect_triage.smoke
```

GitHub Actions runs the same checks for pull requests and pushes to `main`.

## Architecture

```text
Streamlit UI
    -> DefectTriageService
        -> local similarity and recommendation engine
        -> lifecycle and reminder managers
        -> SQLite database
```

The ranking engine combines word-level TF-IDF, character n-grams, component matches,
environment matches, and tag overlap. Recommendations are deterministic and designed to
be easy to explain during a demonstration.

Reminder schedules are persisted in SQLite. They are evaluated when the application runs
or refreshes; no operating-system scheduler or background service is required.

## Repository layout

```text
app.py                         Streamlit application
data/seed.json                 Synthetic knowledge base
src/defect_triage/database.py  SQLite schema and persistence
src/defect_triage/triage.py    Matching and recommendation logic
src/defect_triage/workflow.py  Lifecycle transition rules
src/defect_triage/reminders.py Reminder schedule management
src/defect_triage/service.py   Application use cases
tests/                         Unit and workflow tests
.github/workflows/ci.yml       GitHub Actions CI
```

## GitHub and optional deployment

All source files and synthetic seed data are safe to check into GitHub. The `.gitignore`
excludes the generated database, virtual environments, local secrets, and cache files.

For a shareable hackathon URL, the repository can be connected to Streamlit Community
Cloud. Files written at runtime are not guaranteed to persist there, so a hosted demo will
recreate its SQLite database from seed data after a reset. Local runs retain their data.

## MVP limitations

- Similarity is based on the local synthetic corpus, not a language model.
- Reminders are visible in the app and are not sent externally.
- Reminder checks run only while the application is active or refreshed.
- SQLite is suitable for the local demo, not a multi-user production deployment.
- Authentication and role-based access are outside this MVP.
