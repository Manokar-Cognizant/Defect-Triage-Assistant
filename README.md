# Defect Triage Assistant Agent

A local hackathon MVP that analyzes production defects, finds likely known errors and
historical matches, recommends an owning team and story-point estimate, and manages
follow-up reminders until the defect is closed.

Git repository: https://github.com/Manokar-Cognizant/Defect-Triage-Assistant

The application uses only synthetic defect data. Its optional OpenAI connection is used
only for live semantic similarity analysis; it does not connect to Jira, ServiceNow,
Azure DevOps, email, or messaging systems in the MVP.

Streamlit is the lightweight demonstration interface, not the intended production ticket
entry point. In production, Jira, ServiceNow, Azure DevOps, or another ticketing platform
would call the existing REST service so defects, status changes, assignments, and reminders
stay inside the organization's established workflow. Streamlit could then be removed or
retained as an administrative and troubleshooting dashboard.

## Features

- Live OpenAI similarity agent with `gpt-4o-mini` as the reliable demo default
- Semantic match scores, duplicate classification, and per-match AI rationale
- Explicit offline TF-IDF fallback for demos without network access
- Known-error and likely-duplicate detection
- Similarity-weighted owning-team recommendation
- Historical story-point recommendation on the `1, 2, 3, 5, 8, 13` scale
- Recommendation confidence and supporting evidence
- Agent-activity view for intake, similarity, ownership, estimation, reminders, and lifecycle
- Clickable defect tracker with a unified, chronological agent and lifecycle timeline
- User overrides for team and estimate
- Defect lifecycle and status history
- Recurring in-app follow-up reminders
- Local reminder-email outbox for `manokar.velayutham@cognizant.com`
- Automatic reminder cancellation when a defect is closed
- Synthetic known-error and closed-defect knowledge base
- Persistent local SQLite storage

> **Reminder delivery limitation:** The Send Reminder Agent prepares messages in a local
> email outbox, but it does not send external email because outbound delivery is blocked by
> Cognizant Zscaler in the hackathon environment.

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

### Run the REST API

```powershell
python -m uvicorn defect_triage.api:app --reload --port 8000
```

Interactive API documentation is available at `http://localhost:8000/docs`.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Readiness check |
| `GET` | `/api/defects` | List defects |
| `POST` | `/api/defects` | Create and triage a defect |
| `GET` | `/api/defects/{id}` | Get lifecycle, triage, reminders, and timeline |
| `PATCH` | `/api/defects/{id}/status` | Advance the defect lifecycle |

```http
POST /api/defects
Content-Type: application/json

{"title":"Duplicate order after retry","description":"A timeout caused a retry.","component":"Order Service","environment":"Production","severity":"High","tags":["duplicate","retry"],"similarity_provider":"local","reminder_profile":"Demo"}
```

The response contains the saved defect, triage recommendations, reminders, and complete
timeline. For OpenAI mode, set `similarity_provider` to `openai` and send the key in the
`X-OpenAI-API-Key` header; never commit the key.

Example response shape:

```json
{
  "defect": {"id": 1, "status": "New", "title": "Duplicate order after retry"},
  "triage": {
    "duplicate_classification": "Potential duplicate",
    "recommended_team_name": "Order Platform",
    "recommended_story_points": 5
  },
  "reminder_schedule": {"state": "Active"},
  "timeline": [{"actor": "Intake agent", "event": "Defect logged"}]
}
```

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

1. Select **OpenAI LLM**, enter an API key, and keep `gpt-4o-mini` as the model.
2. Open **New defect** and select **Load demo defect**.
3. Select the **Demo** reminder profile and choose **Analyze and create defect**.
4. Review the AI rationale, known-error match, similar tickets, owner, and story points.
5. Open **Defect tracker**, click the defect row, and show its complete agent timeline.
6. Open **Reminders**, choose **Make next reminder due now**, and preview the prepared email.
7. Return to **Defect tracker**, move the defect through its lifecycle, and close it.
8. Return to **Reminders** and show that future reminders and prepared emails were cancelled.

## Tests and code quality

```powershell
python -m pip install -r requirements-dev.txt
ruff check .
python -m unittest discover -s tests -v
python -m coverage run -m unittest discover -s tests
python -m coverage report --include="src/defect_triage/*"
python -m defect_triage.smoke
```

GitHub Actions runs the same checks for pull requests and pushes to `main`.

## Architecture

```text
Streamlit demo UI or future ticketing-system integration
    -> FastAPI REST controller
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

## Production integration path

The production evolution replaces Streamlit as the primary user interface with Jira or an
equivalent enterprise ticketing tool. That platform sends new defects and lifecycle updates
to the FastAPI endpoints and displays the returned duplicate, owner, estimate, reminder,
and timeline information in the ticket. The core service and agents remain reusable behind
the REST boundary, avoiding a rewrite of the triage logic.

## MVP limitations

- The LLM compares only the included synthetic corpus; it does not search external tickets.
- The selected model is called once per submitted defect through the Responses API. This
  text workflow does not need an audio/WebSocket Realtime session.
- Reminders are visible in the app and are not sent externally.
- Outlook Email exists as a potential connector but is disabled by this organization's
  administrator. Email entries are therefore honest local previews, not delivered messages.
- Reminder checks run only while the application is active or refreshed.
- SQLite is suitable for the local demo, not a multi-user production deployment.
- Authentication and role-based access are outside this MVP.
