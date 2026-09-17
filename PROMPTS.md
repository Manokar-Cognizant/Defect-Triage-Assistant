# Significant Prompt Log

| Phase | Prompt/request | Result and refinement |
|---|---|---|
| Discovery | Build a local Defect Triage Assistant MVP using synthetic data. | Chose Streamlit, Python service layer, SQLite, and an end-to-end workflow. |
| Explainability | Show what the different agents perform. | Added agent activity with evidence and outputs for six logical agents. |
| LLM upgrade | Make the similarity agent call an LLM using an API key and not predefined rules. | Added OpenAI Responses integration, semantic ranking, validation, and masked key entry. |
| Transport | Connection error on the corporate network. | Preserved TLS verification, used the Windows trust store, and switched to a verified HTTP transport. |
| Model access | `gpt-realtime` returned 404. | Switched demo default to accessible `gpt-4o-mini`; retained configurable model input. |
| Lifecycle | Add a tab showing every defect, agent change, and current state. | Added row selection, state cards, and a chronological audit timeline. |
| Reminders | Send follow-up emails to the default Cognizant address. | Outlook connector was admin-disabled; added an honest local email outbox and cancellation behavior. |
| Packaging | Supply required hackathon documentation, REST API, tests, Postman, data, and ZIP. | Added FastAPI facade, three Postman scenarios, 20 synthetic records, and this bundle. |

Prompts were refined toward a small, testable MVP. No API key or private production data is
included in this log.
