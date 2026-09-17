# Problem and Idea

## THEME

Defect Triage Assistant to help TPMs and Managers identify critical bugs, track progress,
and deliver products efficiently.

## IDEA

Agents check defects against the Known Error Database (KEDB), identify the right owning
team, recommend story points based on existing ticket-closure patterns (time and effort),
and create a follow-up reminder schedule that continues until closure.

## HOW_IT_WORKS

A TPM or manager enters a production defect through the Streamlit interface or REST API.
The similarity, ownership, and estimation agents compare it with synthetic KEDB and closed
defect history, then return possible duplicates, the recommended team, story points, and
supporting evidence. Lifecycle and reminder agents persist every change in SQLite, expose a
chronological timeline, schedule follow-ups, and cancel future reminders when the defect is
closed.

Streamlit is used only to demonstrate the workflow quickly. In production, Jira or another
enterprise ticketing tool would replace it as the primary interface and integrate with the
same REST service, keeping defect entry and lifecycle updates in the existing system of
record.

## WHAT_MAKES_IT_DIFFERENT

Instead of producing an unexplained AI answer, the assistant combines live LLM semantic
matching with validated local evidence and an auditable agent timeline. It covers the whole
triage-to-closure workflow while allowing human overrides and an offline similarity mode.

## MEASURED_RESULTS

The local verification suite passes 14 automated tests with 84% measured source-code
coverage. The REST health endpoint and interactive API documentation return HTTP 200, the
sample knowledge base contains 20 synthetic records, and the submission ZIP is under 0.1 MB.
Triage-time improvement against the current manual process has not yet been measured.

## WHY_IT_FITS

The solution directly supports TPMs and managers by surfacing likely critical duplicates,
making ownership and effort recommendations, and keeping follow-ups visible until closure.
It reduces repetitive manual investigation while retaining evidence and human control.

## Repository and demo limitation

- Git repository: https://github.com/Manokar-Cognizant/Defect-Triage-Assistant
- The Send Reminder Agent prepares reminder-email records in a local outbox but does not
  send external email because outbound delivery is blocked by Cognizant Zscaler in the
  hackathon environment.
- Streamlit is the MVP interface; Jira or another ticketing platform is the planned
  production interface through the provided REST API.
