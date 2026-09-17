from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    components_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS known_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    symptoms TEXT NOT NULL,
    component TEXT NOT NULL,
    environment TEXT NOT NULL,
    workaround TEXT NOT NULL,
    team_id TEXT NOT NULL REFERENCES teams(id),
    tags_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_defects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    defect_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    component TEXT NOT NULL,
    environment TEXT NOT NULL,
    team_id TEXT NOT NULL REFERENCES teams(id),
    story_points INTEGER NOT NULL,
    resolution TEXT NOT NULL,
    tags_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS defects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    defect_key TEXT UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    component TEXT NOT NULL,
    environment TEXT NOT NULL,
    severity TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_team_id TEXT REFERENCES teams(id),
    accepted_story_points INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS triage_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    defect_id INTEGER NOT NULL REFERENCES defects(id) ON DELETE CASCADE,
    duplicate_classification TEXT NOT NULL,
    known_matches_json TEXT NOT NULL,
    historical_matches_json TEXT NOT NULL,
    recommended_team_id TEXT REFERENCES teams(id),
    team_confidence REAL NOT NULL,
    recommended_story_points INTEGER NOT NULL,
    story_point_confidence REAL NOT NULL,
    explanation_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    defect_id INTEGER NOT NULL REFERENCES defects(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    changed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminder_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    defect_id INTEGER NOT NULL UNIQUE REFERENCES defects(id) ON DELETE CASCADE,
    profile TEXT NOT NULL,
    cadence_json TEXT NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    next_due_at TEXT,
    last_run_at TEXT,
    created_at TEXT NOT NULL,
    cancelled_at TEXT
);

CREATE TABLE IF NOT EXISTS reminder_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL REFERENCES reminder_schedules(id) ON DELETE CASCADE,
    due_at TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT,
    cancelled_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_defects_status ON defects(status);
CREATE INDEX IF NOT EXISTS idx_reminder_schedules_due ON reminder_schedules(active, next_due_at);
CREATE INDEX IF NOT EXISTS idx_reminder_events_state ON reminder_events(state);
"""


class Database:
    def __init__(self, path: str | Path, seed_path: str | Path):
        self.path = Path(path)
        self.seed_path = Path(seed_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            count = connection.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
            if count == 0:
                self._load_seed(connection)

    def _load_seed(self, connection: sqlite3.Connection) -> None:
        seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        connection.executemany(
            "INSERT INTO teams (id, name, description, components_json) VALUES (?, ?, ?, ?)",
            [
                (
                    team["id"],
                    team["name"],
                    team["description"],
                    json.dumps(team["components"]),
                )
                for team in seed["teams"]
            ],
        )
        connection.executemany(
            """
            INSERT INTO known_errors (
                error_key, title, description, symptoms, component, environment,
                workaround, team_id, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["key"],
                    item["title"],
                    item["description"],
                    item["symptoms"],
                    item["component"],
                    item["environment"],
                    item["workaround"],
                    item["team_id"],
                    json.dumps(item["tags"]),
                )
                for item in seed["known_errors"]
            ],
        )
        connection.executemany(
            """
            INSERT INTO historical_defects (
                defect_key, title, description, component, environment,
                team_id, story_points, resolution, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["key"],
                    item["title"],
                    item["description"],
                    item["component"],
                    item["environment"],
                    item["team_id"],
                    item["story_points"],
                    item["resolution"],
                    json.dumps(item["tags"]),
                )
                for item in seed["historical_defects"]
            ],
        )

    def get_teams(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM teams ORDER BY name").fetchall()
        return [self._decode_row(row, ("components_json",)) for row in rows]

    def get_known_errors(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT k.*, t.name AS team_name
                FROM known_errors k JOIN teams t ON t.id = k.team_id
                ORDER BY k.error_key
                """
            ).fetchall()
        return [self._decode_row(row, ("tags_json",)) for row in rows]

    def get_historical_defects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT h.*, t.name AS team_name
                FROM historical_defects h JOIN teams t ON t.id = h.team_id
                ORDER BY h.defect_key
                """
            ).fetchall()
        return [self._decode_row(row, ("tags_json",)) for row in rows]

    def create_defect(
        self,
        payload: dict[str, Any],
        analysis: dict[str, Any],
        created_at: str,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO defects (
                    title, description, component, environment, severity, tags_json,
                    status, assigned_team_id, accepted_story_points, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'New', ?, ?, ?, ?)
                """,
                (
                    payload["title"],
                    payload["description"],
                    payload["component"],
                    payload["environment"],
                    payload["severity"],
                    json.dumps(payload.get("tags", [])),
                    analysis["recommended_team_id"],
                    analysis["recommended_story_points"],
                    created_at,
                    created_at,
                ),
            )
            defect_id = int(cursor.lastrowid)
            defect_key = f"DEF-{1000 + defect_id}"
            connection.execute(
                "UPDATE defects SET defect_key = ? WHERE id = ?", (defect_key, defect_id)
            )
            connection.execute(
                """
                INSERT INTO triage_runs (
                    defect_id, duplicate_classification, known_matches_json,
                    historical_matches_json, recommended_team_id, team_confidence,
                    recommended_story_points, story_point_confidence,
                    explanation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    defect_id,
                    analysis["duplicate_classification"],
                    json.dumps(analysis["known_matches"]),
                    json.dumps(analysis["historical_matches"]),
                    analysis["recommended_team_id"],
                    analysis["team_confidence"],
                    analysis["recommended_story_points"],
                    analysis["story_point_confidence"],
                    json.dumps(analysis["explanations"]),
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO status_events (defect_id, from_status, to_status, changed_at)
                VALUES (?, NULL, 'New', ?)
                """,
                (defect_id, created_at),
            )
        return defect_id

    def list_defects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.*, t.name AS assigned_team_name
                FROM defects d LEFT JOIN teams t ON t.id = d.assigned_team_id
                ORDER BY d.id DESC
                """
            ).fetchall()
        return [self._decode_row(row, ("tags_json",)) for row in rows]

    def get_defect(self, defect_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT d.*, t.name AS assigned_team_name
                FROM defects d LEFT JOIN teams t ON t.id = d.assigned_team_id
                WHERE d.id = ?
                """,
                (defect_id,),
            ).fetchone()
        return self._decode_row(row, ("tags_json",)) if row else None

    def get_latest_triage(self, defect_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT tr.*, t.name AS recommended_team_name
                FROM triage_runs tr LEFT JOIN teams t ON t.id = tr.recommended_team_id
                WHERE tr.defect_id = ? ORDER BY tr.id DESC LIMIT 1
                """,
                (defect_id,),
            ).fetchone()
        if not row:
            return None
        return self._decode_row(
            row,
            ("known_matches_json", "historical_matches_json", "explanation_json"),
        )

    def get_status_history(self, defect_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM status_events WHERE defect_id = ? ORDER BY id",
                (defect_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_status(
        self,
        defect_id: int,
        from_status: str,
        to_status: str,
        changed_at: str,
    ) -> None:
        closed_at = changed_at if to_status == "Closed" else None
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE defects
                SET status = ?, updated_at = ?, closed_at = ?
                WHERE id = ? AND status = ?
                """,
                (to_status, changed_at, closed_at, defect_id, from_status),
            )
            if connection.total_changes == 0:
                raise ValueError("The defect status changed before this update was applied.")
            connection.execute(
                """
                INSERT INTO status_events (defect_id, from_status, to_status, changed_at)
                VALUES (?, ?, ?, ?)
                """,
                (defect_id, from_status, to_status, changed_at),
            )

    def update_assignment(
        self, defect_id: int, team_id: str, story_points: int, updated_at: str
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE defects
                SET assigned_team_id = ?, accepted_story_points = ?, updated_at = ?
                WHERE id = ?
                """,
                (team_id, story_points, updated_at, defect_id),
            )

    @staticmethod
    def _decode_row(row: sqlite3.Row, json_columns: tuple[str, ...]) -> dict[str, Any]:
        result = dict(row)
        for column in json_columns:
            if column in result:
                result[column.removesuffix("_json")] = json.loads(result.pop(column))
        return result
