from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from defect_triage.llm_similarity import LLMSimilarityError, analyze_defect_with_openai
from defect_triage.service import PROJECT_ROOT, DefectTriageService


class FakeResponses:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.request: dict[str, object] | None = None

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(
            id="resp_test_123",
            output_text=json.dumps(self.payload),
        )


class LLMSimilarityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        service = DefectTriageService(
            database_path=Path(self.temporary_directory.name) / "test.db",
            seed_path=PROJECT_ROOT / "data" / "seed.json",
        )
        self.known_errors = service.list_known_errors()
        self.history = service.list_historical_defects()
        self.defect = {
            "title": "Checkout waits forever after card authorization",
            "description": "The gateway succeeds but the order is not confirmed.",
            "component": "Checkout",
            "environment": "Production",
            "severity": "High",
            "tags": ["payment", "timeout"],
        }

    def test_llm_ranking_drives_similarity_without_local_scoring(self) -> None:
        payload = {
            "duplicate_classification": "Likely known-error match",
            "match_summary": "The payment succeeded but checkout completion was lost.",
            "known_matches": [
                {
                    "key": "KE-1001",
                    "score": 0.97,
                    "match_level": "Strong",
                    "reason": "Same post-authorization checkout timeout.",
                }
            ],
            "historical_matches": [
                {
                    "key": "HIST-2001",
                    "score": 0.93,
                    "match_level": "Strong",
                    "reason": "Same missing completion after gateway callback.",
                }
            ],
        }
        responses = FakeResponses(payload)
        client = SimpleNamespace(responses=responses)

        result = analyze_defect_with_openai(
            self.defect,
            self.known_errors,
            self.history,
            api_key="test-key-not-real",
            model="gpt-realtime",
            client=client,
        )

        self.assertEqual("KE-1001", result["known_matches"][0]["key"])
        self.assertEqual(0.97, result["known_matches"][0]["score"])
        self.assertEqual("payments", result["recommended_team_id"])
        self.assertEqual(5, result["recommended_story_points"])
        self.assertEqual("OpenAI", result["explanations"]["similarity_agent"]["provider"])
        self.assertEqual("resp_test_123", result["explanations"]["similarity_agent"]["response_id"])
        assert responses.request is not None
        self.assertFalse(responses.request["store"])
        self.assertNotIn("test-key-not-real", str(responses.request))

    def test_unknown_model_key_is_rejected(self) -> None:
        payload = {
            "duplicate_classification": "No strong known-error match",
            "match_summary": "No supplied record describes this failure.",
            "known_matches": [
                {
                    "key": "KE-INVENTED",
                    "score": 0.9,
                    "match_level": "Strong",
                    "reason": "Invented.",
                }
            ],
            "historical_matches": [],
        }
        client = SimpleNamespace(responses=FakeResponses(payload))
        with self.assertRaisesRegex(LLMSimilarityError, "unknown key"):
            analyze_defect_with_openai(
                self.defect,
                self.known_errors,
                self.history,
                api_key="test-key-not-real",
                client=client,
            )

    def test_api_key_is_required_for_openai_mode(self) -> None:
        with self.assertRaisesRegex(LLMSimilarityError, "API key"):
            analyze_defect_with_openai(
                self.defect,
                self.known_errors,
                self.history,
                api_key="",
            )


if __name__ == "__main__":
    unittest.main()
