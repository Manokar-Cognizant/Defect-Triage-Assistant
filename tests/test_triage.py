from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from defect_triage.service import PROJECT_ROOT, DefectTriageService


class TriageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        database_path = Path(self.temporary_directory.name) / "test.db"
        self.service = DefectTriageService(
            database_path=database_path,
            seed_path=PROJECT_ROOT / "data" / "seed.json",
        )
        self.now = datetime(2026, 9, 17, 15, 0, tzinfo=UTC)

    def test_seed_data_is_available(self) -> None:
        self.assertEqual(4, len(self.service.list_teams()))
        self.assertEqual(4, len(self.service.list_known_errors()))
        self.assertGreaterEqual(len(self.service.list_historical_defects()), 8)

    def test_checkout_timeout_finds_known_error_and_payments_team(self) -> None:
        defect_id = self.service.create_defect(
            {
                "title": "Checkout times out after gateway authorization",
                "description": (
                    "Customers see a spinner then a timeout during card payment. "
                    "The gateway returned success but the order is not confirmed."
                ),
                "component": "Checkout",
                "environment": "Production",
                "severity": "High",
                "tags": ["payment", "timeout", "gateway", "spinner"],
            },
            reminder_profile="Standard",
            now=self.now,
        )

        detail = self.service.get_defect_detail(defect_id)
        self.assertIsNotNone(detail)
        assert detail is not None
        triage = detail["triage"]
        self.assertEqual("KE-1001", triage["known_matches"][0]["key"])
        self.assertEqual("payments", triage["recommended_team_id"])
        self.assertEqual(5, triage["recommended_story_points"])
        self.assertGreater(triage["team_confidence"], 0.5)

    def test_assignment_can_override_recommendation(self) -> None:
        defect_id = self._create_order_defect()
        self.service.update_assignment(defect_id, "identity", 13, now=self.now)
        detail = self.service.get_defect_detail(defect_id)
        assert detail is not None
        self.assertEqual("identity", detail["defect"]["assigned_team_id"])
        self.assertEqual(13, detail["defect"]["accepted_story_points"])

    def _create_order_defect(self) -> int:
        return self.service.create_defect(
            {
                "title": "Order API made a duplicate after retry",
                "description": (
                    "A response timeout caused the client to retry and create two orders."
                ),
                "component": "Order Service",
                "environment": "Production",
                "severity": "High",
                "tags": ["order", "duplicate", "retry"],
            },
            reminder_profile="Demo",
            now=self.now,
        )


if __name__ == "__main__":
    unittest.main()
