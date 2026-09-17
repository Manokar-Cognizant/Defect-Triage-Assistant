from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

STORY_POINT_SCALE = (1, 2, 3, 5, 8, 13)


def analyze_defect(
    defect: dict[str, Any],
    known_errors: list[dict[str, Any]],
    historical_defects: list[dict[str, Any]],
) -> dict[str, Any]:
    known_matches = _rank(defect, known_errors, limit=3, kind="known")
    historical_matches = _rank(defect, historical_defects, limit=5, kind="historical")

    top_known_score = known_matches[0]["score"] if known_matches else 0.0
    if top_known_score >= 0.58:
        duplicate_classification = "Likely known-error match"
    elif top_known_score >= 0.35:
        duplicate_classification = "Possible known-error match"
    else:
        duplicate_classification = "No strong known-error match"

    team_id, team_confidence, team_reason = _recommend_team(
        defect, known_matches, historical_matches, historical_defects
    )
    points, point_confidence, point_reason = _recommend_story_points(
        defect, historical_matches, historical_defects
    )

    match_reason = (
        f"Top known error {known_matches[0]['key']} scored "
        f"{known_matches[0]['score']:.0%} similarity."
        if known_matches
        else "No known errors were available for comparison."
    )
    return {
        "duplicate_classification": duplicate_classification,
        "known_matches": known_matches,
        "historical_matches": historical_matches,
        "recommended_team_id": team_id,
        "team_confidence": team_confidence,
        "recommended_story_points": points,
        "story_point_confidence": point_confidence,
        "explanations": {
            "match": match_reason,
            "team": team_reason,
            "story_points": point_reason,
        },
    }


def _rank(
    query: dict[str, Any],
    records: list[dict[str, Any]],
    limit: int,
    kind: str,
) -> list[dict[str, Any]]:
    if not records:
        return []

    documents = [_document_text(record) for record in records]
    query_text = _document_text(query)
    combined = [*documents, query_text]

    word_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    character_vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True
    )
    word_matrix = word_vectorizer.fit_transform(combined)
    character_matrix = character_vectorizer.fit_transform(combined)
    word_scores = cosine_similarity(word_matrix[-1], word_matrix[:-1]).ravel()
    character_scores = cosine_similarity(character_matrix[-1], character_matrix[:-1]).ravel()

    scores = (0.7 * word_scores) + (0.3 * character_scores)
    query_component = query.get("component", "").casefold()
    query_environment = query.get("environment", "").casefold()
    query_tags = {tag.casefold() for tag in query.get("tags", [])}

    ranked: list[dict[str, Any]] = []
    for record, raw_score in zip(records, scores, strict=True):
        score = float(raw_score)
        if query_component and query_component == record.get("component", "").casefold():
            score += 0.12
        if query_environment and query_environment == record.get("environment", "").casefold():
            score += 0.03
        record_tags = {tag.casefold() for tag in record.get("tags", [])}
        if query_tags and record_tags:
            score += 0.05 * (len(query_tags & record_tags) / len(query_tags | record_tags))
        score = min(1.0, score)

        match = {
            "key": record.get("error_key", record.get("defect_key")),
            "title": record["title"],
            "component": record["component"],
            "team_id": record["team_id"],
            "team_name": record["team_name"],
            "score": round(score, 4),
            "match_level": _match_level(score),
        }
        if kind == "known":
            match["workaround"] = record["workaround"]
        else:
            match["story_points"] = record["story_points"]
            match["resolution"] = record["resolution"]
        ranked.append(match)

    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]


def _document_text(record: dict[str, Any]) -> str:
    title = record.get("title", "")
    fields = [
        title,
        title,
        record.get("description", ""),
        record.get("symptoms", ""),
        record.get("resolution", ""),
        record.get("component", ""),
        record.get("environment", ""),
        " ".join(record.get("tags", [])),
    ]
    return " ".join(str(field) for field in fields if field)


def _match_level(score: float) -> str:
    if score >= 0.58:
        return "Strong"
    if score >= 0.35:
        return "Moderate"
    return "Weak"


def _recommend_team(
    defect: dict[str, Any],
    known_matches: list[dict[str, Any]],
    historical_matches: list[dict[str, Any]],
    all_history: list[dict[str, Any]],
) -> tuple[str | None, float, str]:
    weights: defaultdict[str, float] = defaultdict(float)
    evidence: defaultdict[str, list[str]] = defaultdict(list)

    for match in historical_matches:
        if match["score"] < 0.12:
            continue
        weight = match["score"] ** 1.5
        weights[match["team_id"]] += weight
        evidence[match["team_id"]].append(match["key"])

    for match in known_matches:
        if match["score"] < 0.3:
            continue
        weight = match["score"] * 0.8
        weights[match["team_id"]] += weight
        evidence[match["team_id"]].append(match["key"])

    component_rows = [
        item
        for item in all_history
        if item["component"].casefold() == defect.get("component", "").casefold()
    ]
    for item in component_rows:
        weights[item["team_id"]] += 0.12

    if not weights:
        return None, 0.0, "The historical data did not contain enough evidence for a team."

    winner = max(weights, key=weights.get)
    total = sum(weights.values())
    top_similarity = max(
        [match["score"] for match in [*known_matches, *historical_matches]], default=0.0
    )
    confidence = min(0.99, (weights[winner] / total) * min(1.0, 0.35 + top_similarity))
    cited = ", ".join(dict.fromkeys(evidence[winner])) or "component ownership history"
    reason = (
        f"Similarity-weighted ownership points to this team using {cited}; "
        f"the component history contributed {len(component_rows)} supporting ticket(s)."
    )
    return winner, round(confidence, 4), reason


def _recommend_story_points(
    defect: dict[str, Any],
    matches: list[dict[str, Any]],
    all_history: list[dict[str, Any]],
) -> tuple[int, float, str]:
    candidates = [match for match in matches if match["score"] >= 0.12]
    if candidates:
        weighted = [
            (match["story_points"], max(match["score"], 0.01), match["key"]) for match in candidates
        ]
        raw_points = _weighted_median([(points, weight) for points, weight, _ in weighted])
        points = _nearest_story_point(raw_points)
        mean_score = float(np.mean([match["score"] for match in candidates]))
        confidence = min(0.95, 0.3 + mean_score + (0.05 if len(candidates) >= 2 else 0.0))
        keys = ", ".join(key for _, _, key in weighted[:3])
        return (
            points,
            round(confidence, 4),
            f"Similarity-weighted median from {keys}, rounded to the supported scale.",
        )

    component_points = [
        item["story_points"]
        for item in all_history
        if item["component"].casefold() == defect.get("component", "").casefold()
    ]
    source = component_points or [item["story_points"] for item in all_history]
    median = float(np.median(source)) if source else 3.0
    return (
        _nearest_story_point(median),
        0.25,
        "No close historical match was found, so the component or global median was used.",
    )


def _weighted_median(values: list[tuple[int, float]]) -> float:
    ordered = sorted(values, key=lambda item: item[0])
    midpoint = sum(weight for _, weight in ordered) / 2
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= midpoint:
            return float(value)
    return float(ordered[-1][0])


def _nearest_story_point(value: float) -> int:
    return min(STORY_POINT_SCALE, key=lambda point: (abs(point - value), point))
