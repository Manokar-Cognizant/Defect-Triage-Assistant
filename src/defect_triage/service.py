from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .database import Database
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
    ) -> int:
        self._validate_payload(payload)
        if reminder_profile not in PROFILES:
            raise ValueError(f"Unknown reminder profile: {reminder_profile}")
        analysis = analyze_defect(
            payload,
            self.database.get_known_errors(),
            self.database.get_historical_defects(),
        )
        timestamp = as_utc_iso(now or utc_now())
        defect_id = self.database.create_defect(payload, analysis, timestamp)
        self.reminders.create_or_reactivate(defect_id, reminder_profile, now)
        return defect_id

    def get_defect_detail(self, defect_id: int) -> dict[str, Any] | None:
        defect = self.database.get_defect(defect_id)
        if not defect:
            return None
        return {
            "defect": defect,
            "triage": self.database.get_latest_triage(defect_id),
            "status_history": self.database.get_status_history(defect_id),
        }

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

    def acknowledge_reminder(self, event_id: int) -> None:
        self.reminders.acknowledge(event_id)

    def force_reminder_due(self, defect_id: int) -> int:
        self.reminders.force_due(defect_id)
        return self.reminders.process_due()

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        required = ("title", "description", "component", "environment", "severity")
        missing = [name for name in required if not str(payload.get(name, "")).strip()]
        if missing:
            raise ValueError(f"Complete these required fields: {', '.join(missing)}")
