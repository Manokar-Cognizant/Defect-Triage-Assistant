from __future__ import annotations

import json
import ssl
import time
from typing import Any

from .triage import complete_analysis

ALLOWED_CLASSIFICATIONS = {
    "Likely known-error match",
    "Possible known-error match",
    "No strong known-error match",
}


class LLMSimilarityError(ValueError):
    """Raised when the live similarity provider cannot return a usable result."""


def analyze_defect_with_openai(
    defect: dict[str, Any],
    known_errors: list[dict[str, Any]],
    historical_defects: list[dict[str, Any]],
    *,
    api_key: str,
    model: str = "gpt-4o-mini",
    client: Any | None = None,
) -> dict[str, Any]:
    if not api_key.strip():
        raise LLMSimilarityError(
            "Enter an OpenAI API key or set OPENAI_API_KEY before using OpenAI LLM mode."
        )
    if not model.strip():
        raise LLMSimilarityError("Enter an OpenAI model name.")

    started = time.perf_counter()
    try:
        prompt = _build_prompt(defect, known_errors, historical_defects)
        if client is None:
            response = _call_responses_api(api_key, model.strip(), prompt)
            raw_text = _response_output_text(response)
            response_id = response.get("id")
        else:
            response = client.responses.create(
                model=model.strip(),
                store=False,
                input=prompt,
            )
            raw_text = getattr(response, "output_text", "")
            response_id = getattr(response, "id", None)
    except Exception as error:
        raise LLMSimilarityError(
            f"OpenAI similarity analysis failed: {_error_details(error)}"
        ) from error

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    parsed = _parse_json_object(raw_text)
    known_matches = _validated_matches(parsed.get("known_matches"), known_errors, "known")
    historical_matches = _validated_matches(
        parsed.get("historical_matches"), historical_defects, "historical"
    )

    classification = str(parsed.get("duplicate_classification", "")).strip()
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise LLMSimilarityError("The model returned an unsupported duplicate classification.")
    match_summary = str(parsed.get("match_summary", "")).strip()
    if not match_summary:
        raise LLMSimilarityError("The model response did not include a match summary.")

    return complete_analysis(
        defect,
        known_matches,
        historical_matches,
        historical_defects,
        duplicate_classification=classification,
        match_reason=match_summary,
        similarity_metadata={
            "provider": "OpenAI",
            "model": model.strip(),
            "response_id": response_id,
            "duration_ms": elapsed_ms,
        },
    )


def _call_responses_api(api_key: str, model: str, prompt: str) -> dict[str, Any]:
    try:
        import httpx
        import truststore
    except ImportError as error:  # pragma: no cover - installation issue
        raise LLMSimilarityError(
            "HTTP dependencies are not installed. Run: pip install -r requirements.txt"
        ) from error

    # Use the operating-system trust store. This keeps TLS verification enabled
    # while supporting managed/corporate Windows networks with a private root CA.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    with httpx.Client(verify=ssl_context, timeout=30.0) as http_client:
        response = http_client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "input": prompt, "store": False},
        )

    if response.is_error:
        try:
            message = response.json().get("error", {}).get("message")
        except (ValueError, AttributeError):
            message = None
        detail = message or response.reason_phrase
        if response.status_code == 404 and model == "gpt-realtime":
            detail += " Choose gpt-4o-mini in the sidebar for the hackathon demo."
        raise LLMSimilarityError(f"OpenAI API returned HTTP {response.status_code}: {detail}")

    payload = response.json()
    if not isinstance(payload, dict):
        raise LLMSimilarityError("OpenAI returned an unexpected response body.")
    return payload


def _response_output_text(response: dict[str, Any]) -> str:
    texts: list[str] = []
    for output in response.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                texts.append(str(content.get("text", "")))
    if not texts:
        raise LLMSimilarityError("OpenAI returned no text output.")
    return "\n".join(texts)


def _build_prompt(
    defect: dict[str, Any],
    known_errors: list[dict[str, Any]],
    historical_defects: list[dict[str, Any]],
) -> str:
    payload = {
        "new_defect": defect,
        "known_errors": [_candidate(item, "known") for item in known_errors],
        "historical_closed_defects": [
            _candidate(item, "historical") for item in historical_defects
        ],
    }
    return f"""You are the Similarity Agent in a production defect-triage workflow.
Use semantic reasoning over the full meaning, symptoms, component, environment, and tags.
Do not use keyword-counting rules. Compare the new defect with every supplied candidate.
Never invent keys or facts. Scores are calibrated semantic similarity from 0.0 to 1.0.

Return ONLY one JSON object with this exact shape:
{{
  "duplicate_classification":
    "Likely known-error match | Possible known-error match | No strong known-error match",
  "match_summary": "brief evidence-based explanation",
  "known_matches": [
    {{"key": "existing key", "score": 0.0,
      "match_level": "Strong | Moderate | Weak", "reason": "why"}}
  ],
  "historical_matches": [
    {{"key": "existing key", "score": 0.0,
      "match_level": "Strong | Moderate | Weak", "reason": "why"}}
  ]
}}

Return at most 3 known-error matches and 5 historical matches, ordered most similar first.
Include weak candidates only when they help explain the comparison.

INPUT DATA:
{json.dumps(payload, ensure_ascii=False)}
"""


def _candidate(record: dict[str, Any], kind: str) -> dict[str, Any]:
    fields = {
        "key": record.get("error_key", record.get("defect_key")),
        "title": record.get("title"),
        "description": record.get("description"),
        "component": record.get("component"),
        "environment": record.get("environment"),
        "tags": record.get("tags", []),
    }
    if kind == "known":
        fields["symptoms"] = record.get("symptoms")
    else:
        fields["resolution"] = record.get("resolution")
    return fields


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError) as error:
        raise LLMSimilarityError("The model returned invalid JSON. Please retry.") from error
    if not isinstance(value, dict):
        raise LLMSimilarityError("The model response must be a JSON object.")
    return value


def _error_details(error: Exception) -> str:
    """Expose safe nested transport details without ever including request credentials."""
    parts: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(parts) < 4:
        seen.add(id(current))
        message = str(current).strip() or "No additional detail"
        parts.append(f"{type(current).__name__}: {message}")
        current = current.__cause__ or current.__context__
    return " Caused by ".join(parts)


def _validated_matches(
    raw_matches: Any,
    records: list[dict[str, Any]],
    kind: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw_matches, list):
        raise LLMSimilarityError(f"The model response omitted {kind} matches.")

    by_key = {
        str(record.get("error_key", record.get("defect_key"))): record for record in records
    }
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    limit = 3 if kind == "known" else 5
    for raw in raw_matches:
        if not isinstance(raw, dict):
            raise LLMSimilarityError("A model match was not a JSON object.")
        key = str(raw.get("key", ""))
        if key not in by_key:
            raise LLMSimilarityError(f"The model invented or returned an unknown key: {key}")
        if key in seen:
            continue
        try:
            score = float(raw["score"])
        except (KeyError, TypeError, ValueError) as error:
            raise LLMSimilarityError(f"The model returned an invalid score for {key}.") from error
        if not 0.0 <= score <= 1.0:
            raise LLMSimilarityError(f"The model returned an out-of-range score for {key}.")
        match_level = str(raw.get("match_level", "")).strip()
        if match_level not in {"Strong", "Moderate", "Weak"}:
            raise LLMSimilarityError(f"The model returned an invalid match level for {key}.")

        record = by_key[key]
        match = {
            "key": key,
            "title": record["title"],
            "component": record["component"],
            "team_id": record["team_id"],
            "team_name": record["team_name"],
            "score": round(score, 4),
            "match_level": match_level,
            "reason": str(raw.get("reason", "")).strip(),
        }
        if kind == "known":
            match["workaround"] = record["workaround"]
        else:
            match["story_points"] = record["story_points"]
            match["resolution"] = record["resolution"]
        validated.append(match)
        seen.add(key)
        if len(validated) == limit:
            break

    return validated
