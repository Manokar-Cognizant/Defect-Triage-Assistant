# Defect Triage Assistant Agent

A local hackathon MVP that analyzes production defects, finds likely known errors and
historical matches, recommends an owning team and story-point estimate, and manages
follow-up reminders until the defect is closed.

The application uses only synthetic defect data. Its optional OpenAI connection is used
only for live semantic similarity analysis; it does not connect to Jira, ServiceNow,
Azure DevOps, email, or messaging systems.

## Features

- Live OpenAI similarity agent with `gpt-realtime` as the default model
- Semantic match scores, duplicate classification, and per-match AI rationale
- Explicit offline TF-IDF fallback for demos without network access
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

## Configure the OpenAI similarity agent

Choose **OpenAI LLM** in the sidebar and paste your API key into the masked field, or set
it before starting Streamlit:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
streamlit run app.py
```

The key is held only in process/browser-session memory. It is never stored in SQLite,
logged by the application, or committed to Git. The app requests `store=False` for model
responses. The model name is editable in the sidebar if your OpenAI project enables a
different model.

## Suggested demo

1. Select **OpenAI LLM**, enter an API key, and keep `gpt-realtime` as the model.
2. Open **New defect** and select **Load demo defect**.
3. Select the **Demo** reminder profile and choose **Analyze and create defect**.
4. Review the AI rationale, known-error match, similar tickets, owner, and story points.
5. Open **Agent activity** to show the provider, model, and every specialist stage.
6. Open **Reminders** and choose **Make next reminder due now**.
7. Open **Defect tracker**, move the defect through its lifecycle, and close it.
8. Return to **Reminders** and show that future reminders were cancelled.

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
        -> OpenAI Responses API similarity agent (or explicit local fallback)
        -> local ownership and story-point recommendation engine
        -> lifecycle and reminder managers
        -> SQLite database
```

In OpenAI mode, the similarity agent sends the new defect and the synthetic candidate
records to the selected model for semantic ranking. The application validates returned
keys and scores against its local corpus before using those matches for deterministic,
explainable team and story-point recommendations. It never silently falls back to local
rules when an OpenAI call fails.

Reminder schedules are persisted in SQLite. They are evaluated when the application runs
or refreshes; no operating-system scheduler or background service is required.

## Repository layout

```text
app.py                         Streamlit application
data/seed.json                 Synthetic knowledge base
src/defect_triage/database.py  SQLite schema and persistence
src/defect_triage/llm_similarity.py OpenAI prompt, call, and response validation
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

- The LLM compares only the included synthetic corpus; it does not search external tickets.
- `gpt-realtime` is called once per submitted defect through the Responses API; this MVP
  does not need an audio/WebSocket session.
- Reminders are visible in the app and are not sent externally.
- Reminder checks run only while the application is active or refreshed.
- SQLite is suitable for the local demo, not a multi-user production deployment.
- Authentication and role-based access are outside this MVP.
