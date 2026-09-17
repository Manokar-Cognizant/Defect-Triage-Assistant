# Architecture

## Before: legacy manual/batch flow

```mermaid
flowchart LR
  A[Production alerts and tickets] --> B[Nightly export]
  B --> C[Batch report]
  C --> D[Engineer searches old tickets]
  D --> E[Spreadsheet owner and estimate]
  E --> F[Manual calendar/email follow-up]
```

## After: agent-assisted service

```mermaid
flowchart LR
  U[Streamlit demo UI] --> C[FastAPI controller + DTO validation]
  P[Jira or enterprise ticketing tool] -. Production replacement for demo UI .-> C
  C --> S[DefectTriageService]
  S --> L[OpenAI similarity agent]
  S --> O[Ownership + estimation agents]
  S --> R[Reminder + lifecycle agents]
  L --> DB[(SQLite + synthetic dataset)]
  O --> DB
  R --> DB
  DB --> T[Unified audit timeline]
  DB --> E[Local email outbox]
```

The REST controller is stateless; service rules own use cases; SQLite stores demo state.
The API key remains in memory and model responses are requested with `store=false`.
Streamlit accelerates the hackathon demonstration. In production, Jira, ServiceNow, Azure
DevOps, or another ticketing system becomes the primary interface and calls the same REST
contract; Streamlit can be removed or retained as an administrative dashboard.
