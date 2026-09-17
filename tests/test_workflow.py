from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from defect_triage.reminders import DEFAULT_REMINDER_EMAIL
from defect_triage.service import PROJECT_ROOT, DefectTriageService


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.service = DefectTriageService(
            database_path=Path(self.temporary_directory.name) / "test.db",
            seed_path=PROJECT_ROOT / "data" / "seed.json",
        )
        self.now = datetime(2026, 9, 17, 15, 0, tzinfo=UTC)
        self.defect_id = self.service.create_defect(
            {
                "title": "SSO redirects back to login",
                "description": (
                    "Login succeeds but the new token is immediately considered expired."
                ),
                "component": "SSO",
                "environment": "Production",
                "severity": "Medium",
                "tags": ["sso", "login", "token"],
            },
            reminder_profile="Demo",
            now=self.now,
        )

    def test_invalid_status_transition_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.change_status(self.defect_id, "Resolved", now=self.now)

    def test_closing_cancels_schedule_and_due_reminder(self) -> None:
        due_time = self.now + timedelta(seconds=31)
        self.assertEqual(1, self.service.process_due_reminders(due_time))
        self.assertEqual("Due", self.service.list_reminder_events()[0]["state"])

        self.service.change_status(self.defect_id, "Closed", now=due_time + timedelta(seconds=1))

        schedule = self.service.list_reminder_schedules()[0]
        event = self.service.list_reminder_events()[0]
        email = self.service.list_reminder_emails()[0]
        self.assertEqual(0, schedule["active"])
        self.assertIsNone(schedule["next_due_at"])
        self.assertEqual("Cancelled", event["state"])
        self.assertEqual("Cancelled", email["state"])

    def test_reopening_reactivates_reminders(self) -> None:
        self.service.change_status(self.defect_id, "Closed", now=self.now)
        self.service.change_status(
            self.defect_id, "In Progress", now=self.now + timedelta(minutes=1)
        )
        schedule = self.service.list_reminder_schedules()[0]
        self.assertEqual(1, schedule["active"])
        self.assertEqual("Demo", schedule["profile"])

    def test_due_reminder_can_be_acknowledged(self) -> None:
        self.service.process_due_reminders(self.now + timedelta(seconds=31))
        event = self.service.list_reminder_events()[0]
        self.service.acknowledge_reminder(event["id"])
        self.assertEqual("Acknowledged", self.service.list_reminder_events()[0]["state"])

    def test_due_reminder_prepares_default_email_preview(self) -> None:
        self.service.process_due_reminders(self.now + timedelta(seconds=31))
        email = self.service.list_reminder_emails()[0]
        self.assertEqual(DEFAULT_REMINDER_EMAIL, email["recipient"])
        self.assertEqual("Prepared", email["state"])
        self.assertEqual("Local preview", email["delivery_mode"])

    def test_tracker_timeline_contains_agent_work_and_current_changes(self) -> None:
        self.service.update_assignment(self.defect_id, "payments", 8, now=self.now)
        detail = self.service.get_defect_detail(self.defect_id)
        assert detail is not None
        actors = {item["actor"] for item in detail["timeline"]}
        self.assertIn("Intake agent", actors)
        self.assertIn("Similarity agent", actors)
        self.assertIn("Ownership agent", actors)
        self.assertIn("Estimation agent", actors)
        self.assertIn("Reminder agent", actors)
        self.assertIn("Triage user", actors)


if __name__ == "__main__":
    unittest.main()
