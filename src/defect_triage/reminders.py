from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import Database


PROFILES: dict[str, tuple[int, ...]] = {
    "Demo": (30, 60, 120),
    "Standard": (24 * 60 * 60, 3 * 24 * 60 * 60, 7 * 24 * 60 * 60),
}
DEFAULT_REMINDER_EMAIL = "manokar.velayutham@cognizant.com"


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class ReminderManager:
    def __init__(self, database: Database):
        self.database = database

    def create_or_reactivate(
        self,
        defect_id: int,
        profile: str,
        now: datetime | None = None,
    ) -> None:
        now = now or utc_now()
        cadence = PROFILES[profile]
        next_due = now + timedelta(seconds=cadence[0])
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO reminder_schedules (
                    defect_id, profile, cadence_json, step_index, active,
                    next_due_at, created_at, cancelled_at
                ) VALUES (?, ?, ?, 0, 1, ?, ?, NULL)
                ON CONFLICT(defect_id) DO UPDATE SET
                    profile = excluded.profile,
                    cadence_json = excluded.cadence_json,
                    step_index = 0,
                    active = 1,
                    next_due_at = excluded.next_due_at,
                    cancelled_at = NULL
                """,
                (
                    defect_id,
                    profile,
                    json.dumps(cadence),
                    as_utc_iso(next_due),
                    as_utc_iso(now),
                ),
            )
            connection.execute(
                """
                INSERT INTO defect_events (
                    defect_id, actor, event_type, summary, details_json, created_at
                ) VALUES (?, 'Reminder agent', 'Schedule activated', ?, ?, ?)
                """,
                (
                    defect_id,
                    f"{profile} follow-up schedule activated",
                    json.dumps(
                        {
                            "profile": profile,
                            "recipient": DEFAULT_REMINDER_EMAIL,
                            "next_due_at": as_utc_iso(next_due),
                        }
                    ),
                    as_utc_iso(now),
                ),
            )

    def process_due(self, now: datetime | None = None) -> int:
        now = now or utc_now()
        now_iso = as_utc_iso(now)
        created = 0
        with self.database.connect() as connection:
            schedules = connection.execute(
                """
                SELECT rs.*, d.status, d.defect_key, d.title
                FROM reminder_schedules rs JOIN defects d ON d.id = rs.defect_id
                WHERE rs.active = 1 AND rs.next_due_at <= ?
                """,
                (now_iso,),
            ).fetchall()
            for schedule in schedules:
                if schedule["status"] == "Closed":
                    self._cancel_in_connection(connection, schedule["defect_id"], now_iso)
                    continue
                cursor = connection.execute(
                    """
                    INSERT INTO reminder_events (schedule_id, due_at, state, created_at)
                    VALUES (?, ?, 'Due', ?)
                    """,
                    (schedule["id"], schedule["next_due_at"], now_iso),
                )
                reminder_event_id = int(cursor.lastrowid)
                subject = f"Defect follow-up: {schedule['defect_key']} — {schedule['title']}"
                body = (
                    f"Follow-up is due for {schedule['defect_key']}: {schedule['title']}.\n\n"
                    f"Current status: {schedule['status']}\n"
                    "Please review the defect and update its lifecycle state."
                )
                connection.execute(
                    """
                    INSERT INTO reminder_emails (
                        reminder_event_id, defect_id, recipient, subject, body,
                        delivery_mode, state, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'Local preview', 'Prepared', ?)
                    """,
                    (
                        reminder_event_id,
                        schedule["defect_id"],
                        DEFAULT_REMINDER_EMAIL,
                        subject,
                        body,
                        now_iso,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO defect_events (
                        defect_id, actor, event_type, summary, details_json, created_at
                    ) VALUES (?, 'Reminder agent', 'Follow-up due', ?, ?, ?)
                    """,
                    (
                        schedule["defect_id"],
                        f"Reminder email prepared for {DEFAULT_REMINDER_EMAIL}",
                        json.dumps(
                            {
                                "delivery_mode": "Local preview",
                                "delivery_state": "Prepared",
                                "subject": subject,
                            }
                        ),
                        now_iso,
                    ),
                )
                cadence = json.loads(schedule["cadence_json"])
                next_step = min(schedule["step_index"] + 1, len(cadence) - 1)
                next_due = now + timedelta(seconds=cadence[next_step])
                connection.execute(
                    """
                    UPDATE reminder_schedules
                    SET step_index = ?, next_due_at = ?, last_run_at = ?
                    WHERE id = ?
                    """,
                    (next_step, as_utc_iso(next_due), now_iso, schedule["id"]),
                )
                created += 1
        return created

    def cancel(self, defect_id: int, now: datetime | None = None) -> None:
        now_iso = as_utc_iso(now or utc_now())
        with self.database.connect() as connection:
            self._cancel_in_connection(connection, defect_id, now_iso)

    @staticmethod
    def _cancel_in_connection(connection: Any, defect_id: int, now_iso: str) -> None:
        schedule = connection.execute(
            "SELECT id FROM reminder_schedules WHERE defect_id = ?", (defect_id,)
        ).fetchone()
        if not schedule:
            return
        connection.execute(
            """
            UPDATE reminder_schedules
            SET active = 0, next_due_at = NULL, cancelled_at = ?
            WHERE defect_id = ?
            """,
            (now_iso, defect_id),
        )
        connection.execute(
            """
            UPDATE reminder_events
            SET state = 'Cancelled', cancelled_at = ?
            WHERE schedule_id = ? AND state = 'Due'
            """,
            (now_iso, schedule["id"]),
        )
        connection.execute(
            """
            UPDATE reminder_emails
            SET state = 'Cancelled', cancelled_at = ?
            WHERE defect_id = ? AND state = 'Prepared'
            """,
            (now_iso, defect_id),
        )
        connection.execute(
            """
            INSERT INTO defect_events (
                defect_id, actor, event_type, summary, details_json, created_at
            ) VALUES (?, 'Reminder agent', 'Schedule cancelled',
                      'Future follow-up reminders cancelled', '{}', ?)
            """,
            (defect_id, now_iso),
        )

    def acknowledge(self, event_id: int, now: datetime | None = None) -> None:
        changed_at = as_utc_iso(now or utc_now())
        with self.database.connect() as connection:
            event = connection.execute(
                """
                SELECT rs.defect_id
                FROM reminder_events re
                JOIN reminder_schedules rs ON rs.id = re.schedule_id
                WHERE re.id = ?
                """,
                (event_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE reminder_events
                SET state = 'Acknowledged', acknowledged_at = ?
                WHERE id = ? AND state = 'Due'
                """,
                (changed_at, event_id),
            )
            if event:
                connection.execute(
                    """
                    INSERT INTO defect_events (
                        defect_id, actor, event_type, summary, details_json, created_at
                    ) VALUES (?, 'Reminder agent', 'Reminder acknowledged',
                              'Due reminder acknowledged', '{}', ?)
                    """,
                    (event["defect_id"], changed_at),
                )

    def force_due(self, defect_id: int, now: datetime | None = None) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE reminder_schedules SET next_due_at = ?
                WHERE defect_id = ? AND active = 1
                """,
                (as_utc_iso(now or utc_now()), defect_id),
            )

    def list_schedules(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT rs.*, d.defect_key, d.title, d.status AS defect_status
                FROM reminder_schedules rs JOIN defects d ON d.id = rs.defect_id
                ORDER BY rs.active DESC, rs.next_due_at, rs.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_events(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT re.*, d.id AS defect_id, d.defect_key, d.title
                FROM reminder_events re
                JOIN reminder_schedules rs ON rs.id = re.schedule_id
                JOIN defects d ON d.id = rs.defect_id
                ORDER BY re.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]
