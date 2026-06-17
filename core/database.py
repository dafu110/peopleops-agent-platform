import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .config import get_settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'hrbp',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interview_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_name TEXT NOT NULL,
    interview_time TEXT NOT NULL,
    status TEXT NOT NULL,
    email_draft_path TEXT,
    calendar_event_path TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    expected_keywords TEXT NOT NULL,
    retrieved_sources TEXT NOT NULL,
    passed INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.db_path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT OR IGNORE INTO users (username, role, created_at)
            VALUES (?, ?, ?)
            """,
            ("local-admin", "admin", utc_now()),
        )


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    init_db()
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_interview_action(
    *,
    candidate_name: str,
    interview_time: str,
    status: str,
    email_draft_path: Optional[Path],
    calendar_event_path: Optional[Path],
    created_by: str,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO interview_actions (
                candidate_name,
                interview_time,
                status,
                email_draft_path,
                calendar_event_path,
                created_by,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_name,
                interview_time,
                status,
                str(email_draft_path) if email_draft_path else None,
                str(calendar_event_path) if calendar_event_path else None,
                created_by,
                utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def list_interview_actions(limit: int = 20) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM interview_actions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_rag_evaluation(
    *,
    question: str,
    expected_keywords: str,
    retrieved_sources: str,
    passed: bool,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO rag_evaluations (
                question,
                expected_keywords,
                retrieved_sources,
                passed,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (question, expected_keywords, retrieved_sources, int(passed), utc_now()),
        )
        return int(cursor.lastrowid)
