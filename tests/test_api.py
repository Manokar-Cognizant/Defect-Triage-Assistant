from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from defect_triage.api import app
from defect_triage.service import PROJECT_ROOT, DefectTriageService


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        app.state.service = DefectTriageService(
            database_path=Path(self.temporary_directory.name) / "api-test.db",
            seed_path=PROJECT_ROOT / "data" / "seed.json",
        )
        self.client = TestClient(app)

    def test_create_list_get_and_reject_invalid_transition(self) -> None:
        response = self.client.post(
            "/api/defects",
            json={
                "title": "Duplicate order after retry",
                "description": "A response timeout caused the order request to be retried.",
                "component": "Order Service",
                "environment": "Production",
                "severity": "High",
                "tags": ["duplicate", "retry"],
                "reminder_profile": "Demo",
                "similarity_provider": "local",
            },
        )
        self.assertEqual(201, response.status_code)
        defect_id = response.json()["defect"]["id"]
        self.assertEqual(1, len(self.client.get("/api/defects").json()))
        self.assertEqual(200, self.client.get(f"/api/defects/{defect_id}").status_code)
        invalid = self.client.patch(
            f"/api/defects/{defect_id}/status", json={"status": "Resolved"}
        )
        self.assertEqual(422, invalid.status_code)

    def test_validation_and_missing_defect(self) -> None:
        self.assertEqual(422, self.client.post("/api/defects", json={}).status_code)
        self.assertEqual(404, self.client.get("/api/defects/999").status_code)


if __name__ == "__main__":
    unittest.main()
