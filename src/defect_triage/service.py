from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .database import Database
from .llm_similarity import analyze_defect_with_openai
from .reminders import PROFILES, ReminderManager, as_utc_iso, utc_now
from .triage import STORY_POINT_SCALE, analyze_defect
from .workflow import allowed_transitions, validate_transition

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DefectTriageService:
    def __init__(
        self,
        database_path: str | Path | None = None,
        seed_path: str | Path | None = None,
    ):
        self.database = Database(
            database_path or PROJECT_ROOT / "data" / "defect_triage.db",
            seed_path or PROJECT_ROOT / "data" / "seed.json",
        )
        self.database.initialize()
        self.reminders = ReminderManager(self.database)

    def create_defect(
        self,
        payload: dict[str, Any],
        reminder_profile: str = "Standard",
        now: datetime | None = None,
        similarity_provider: str = "local",
        api_key: str = "",
        model: str = "gpt-4o-mini",
    ) -> int:
        self._validate_payload(payload)
        if reminder_profile not in PROFILES:
            raise ValueError(f"Unknown reminder profile: {reminder_profile}")
        known_errors = self.database.get_known_errors()
        historical_defects = self.database.get_historical_defects()
        if similarity_provider == "openai":
            analysis = analyze_defect_with_openai(
                payload,
                known_errors,
                historical_defects,
                api_key=api_key,
                model=model,
            )
        elif similarity_provider == "local":
            analysis = analyze_defect(payload, known_errors, historical_defects)
        else:
            raise ValueError(f"Unknown similarity provider: {similarity_provider}")
        timestamp = as_utc_iso(now or utc_now())
        defect_id = self.database.create_defect(payload, analysis, timestamp)
        self.reminders.create_or_reactivate(defect_id, reminder_profile, now)
        return defect_id

    def get_defect_detail(self, defect_id: int) -> dict[str, Any] | None:
        defect = self.database.get_defect(defect_id)
        if not defect:
            return None
        triage = self.database.get_latest_triage(defect_id)
        status_history = self.database.get_status_history(defect_id)
        schedules = self.reminders.list_schedules()
        schedule = next((item for item in schedules if item["defect_id"] == defect_id), None)
        reminder_events = [
            item for item in self.reminders.list_events() if item["defect_id"] == defect_id
        ]
        emails = [
            item for item in self.database.list_reminder_emails() if item["defect_id"] == defect_id
        ]
        audit_events = self.database.get_defect_events(defect_id)
        detail = {
            "defect": defect,
            "triage": triage,
            "status_history": status_history,
            "reminder_schedule": schedule,
            "reminder_events": reminder_events,
            "reminder_emails": emails,
        }
        detail["timeline"] = self._build_timeline(detail, audit_events)
        return detail

    def list_defects(self) -> list[dict[str, Any]]:
        return self.database.list_defects()

    def list_teams(self) -> list[dict[str, Any]]:
        return self.database.get_teams()

    def list_known_errors(self) -> list[dict[str, Any]]:
        return self.database.get_known_errors()

    def list_historical_defects(self) -> list[dict[str, Any]]:
        return self.database.get_historical_defects()

    def list_components(self) -> list[str]:
        components = {
            component for team in self.list_teams() for component in team.get("components", [])
        }
        return sorted(components)

    def change_status(
        self,
        defect_id: int,
        to_status: str,
        now: datetime | None = None,
    ) -> None:
        defect = self.database.get_defect(defect_id)
        if not defect:
            raise ValueError("Defect not found.")
        from_status = defect["status"]
        validate_transition(from_status, to_status)
        timestamp = now or utc_now()
        self.database.update_status(defect_id, from_status, to_status, as_utc_iso(timestamp))
        if to_status == "Closed":
            self.reminders.cancel(defect_id, timestamp)
        elif from_status == "Closed":
            profile = "Standard"
            schedule = next(
                (
                    item
                    for item in self.reminders.list_schedules()
                    if item["defect_id"] == defect_id
                ),
                None,
            )
            if schedule:
                profile = schedule["profile"]
            self.reminders.create_or_reactivate(defect_id, profile, timestamp)

    def available_statuses(self, status: str) -> tuple[str, ...]:
        return allowed_transitions(status)

    def update_assignment(
        self,
        defect_id: int,
        team_id: str,
        story_points: int,
        now: datetime | None = None,
    ) -> None:
        team_ids = {team["id"] for team in self.list_teams()}
        if team_id not in team_ids:
            raise ValueError("Unknown team.")
        if story_points not in STORY_POINT_SCALE:
            raise ValueError("Story points must use the supported scale.")
        self.database.update_assignment(
            defect_id, team_id, story_points, as_utc_iso(now or utc_now())
        )

    def process_due_reminders(self, now: datetime | None = None) -> int:
        return self.reminders.process_due(now)

    def list_reminder_schedules(self) -> list[dict[str, Any]]:
        return self.reminders.list_schedules()

    def list_reminder_events(self) -> list[dict[str, Any]]:
        return self.reminders.list_events()

    def list_reminder_emails(self) -> list[dict[str, Any]]:
        return self.database.list_reminder_emails()

    def acknowledge_reminder(self, event_id: int) -> None:
        self.reminders.acknowledge(event_id)

    def force_reminder_due(self, defect_id: int) -> int:
        self.reminders.force_due(defect_id)
        return self.reminders.process_due()

    @staticmethod
    def _build_timeline(
        detail: dict[str, Any], audit_events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        defect = detail["defect"]
        triage = detail["triage"]
        timeline: list[dict[str, Any]] = [
            {
                "occurred_at": defect["created_at"],
                "sequence": 10,
                "actor": "Intake agent",
                "event": "Defect logged",
                "summary": (
                    f"{defect['severity']} defect logged for {defect['component']} "
                    f"in {defect['environment']}"
                ),
                "details": {"tags": defect["tags"]},
            }
        ]
        if triage:
            explanation = triage["explanation"]
            similarity = explanation.get("similarity_agent", {})
            top_known = triage["known_matches"][0] if triage["known_matches"] else None
            timeline.extend(
                [
                    {
                        "occurred_at": triage["created_at"],
                        "sequence": 20,
                        "actor": "Similarity agent",
                        "event": "Similarity analysis",
                        "summary": triage["duplicate_classification"],
                        "details": {
                            "provider": similarity.get("provider", "Local"),
                            "model": similarity.get("model"),
                            "top_match": top_known["key"] if top_known else None,
                            "rationale": explanation["match"],
                        },
                    },
                    {
                        "occurred_at": triage["created_at"],
                        "sequence": 30,
                        "actor": "Ownership agent",
                        "event": "Owner recommended",
                        "summary": (
                            f"Recommended {triage.get('recommended_team_name') or 'manual triage'} "
                            f"at {triage['team_confidence']:.0%} confidence"
                        ),
                        "details": {"rationale": explanation["team"]},
                    },
                    {
                        "occurred_at": triage["created_at"],
                        "sequence": 40,
                        "actor": "Estimation agent",
                        "event": "Estimate recommended",
                        "summary": (
                            f"Recommended {triage['recommended_story_points']} story points "
                            f"at {triage['story_point_confidence']:.0%} confidence"
                        ),
                        "details": {"rationale": explanation["story_points"]},
                    },
                ]
            )

        schedule = detail["reminder_schedule"]
        has_schedule_audit = any(
            item["event_type"] == "Schedule activated" for item in audit_events
        )
        if schedule and not has_schedule_audit:
            timeline.append(
                {
                    "occurred_at": schedule["created_at"],
                    "sequence": 50,
                    "actor": "Reminder agent",
                    "event": "Schedule activated",
                    "summary": f"{schedule['profile']} follow-up schedule activated",
                    "details": {"next_due_at": schedule["next_due_at"]},
                }
            )

        for event in detail["status_history"]:
            if event["from_status"] is None:
                continue
            timeline.append(
                {
                    "occurred_at": event["changed_at"],
                    "sequence": 70,
                    "actor": "Lifecycle agent",
                    "event": "Status changed",
                    "summary": f"{event['from_status']} → {event['to_status']}",
                    "details": {},
                }
            )
        for event in audit_events:
            timeline.append(
                {
                    "occurred_at": event["created_at"],
                    "sequence": 60,
                    "actor": event["actor"],
                    "event": event["event_type"],
                    "summary": event["summary"],
                    "details": event["details"],
                }
            )
        for email in detail["reminder_emails"]:
            timeline.append(
                {
                    "occurred_at": email["created_at"],
                    "sequence": 65,
                    "actor": "Email outbox",
                    "event": email["state"],
                    "summary": f"{email['subject']} → {email['recipient']}",
                    "details": {"delivery_mode": email["delivery_mode"]},
                }
            )
        return sorted(timeline, key=lambda item: (item["occurred_at"], item["sequence"]))

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        required = ("title", "description", "component", "environment", "severity")
        missing = [name for name in required if not str(payload.get(name, "")).strip()]
        if missing:
            raise ValueError(f"Complete these required fields: {', '.join(missing)}")
