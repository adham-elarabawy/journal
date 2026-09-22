from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Memo


class JournalStore:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "journal.sqlite3"
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS memos (
                memo_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                title TEXT,
                duration_seconds REAL,
                transcript TEXT,
                transcript_model TEXT,
                transcription_error TEXT,
                transcription_error_at TEXT,
                transcription_attempts INTEGER NOT NULL DEFAULT 0,
                journal_status TEXT NOT NULL DEFAULT 'unknown',
                journal_confidence REAL,
                journal_reason TEXT,
                status_is_manual INTEGER NOT NULL DEFAULT 0,
                analyzed_at TEXT,
                analysis_note TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS memos_recorded_at ON memos(recorded_at DESC);
            CREATE INDEX IF NOT EXISTS memos_journal_status ON memos(journal_status);
            """
        )
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(memos)").fetchall()
        }
        additions = {
            "transcription_error": "TEXT",
            "transcription_error_at": "TEXT",
            "transcription_attempts": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.connection.execute(f"ALTER TABLE memos ADD COLUMN {name} {definition}")
        self.connection.commit()

    def upsert_scanned(self, memos: list[Memo]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connection.executemany(
            """
            INSERT INTO memos (
                memo_id, path, recorded_at, title, duration_seconds, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(memo_id) DO UPDATE SET
                path = excluded.path,
                recorded_at = excluded.recorded_at,
                title = COALESCE(excluded.title, memos.title),
                duration_seconds = COALESCE(excluded.duration_seconds, memos.duration_seconds),
                updated_at = excluded.updated_at
            """,
            [
                (
                    memo.memo_id,
                    str(memo.path),
                    memo.recorded_at.isoformat(),
                    memo.title,
                    memo.duration_seconds,
                    now,
                )
                for memo in memos
            ],
        )
        self.connection.commit()

    def list_recent(self, limit: int = 50) -> list[Memo]:
        rows = self.connection.execute(
            "SELECT * FROM memos ORDER BY recorded_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_memo(row) for row in rows]

    def get(self, memo_id: str) -> Memo | None:
        row = self.connection.execute(
            "SELECT * FROM memos WHERE memo_id = ?", (memo_id,)
        ).fetchone()
        return self._row_to_memo(row) if row else None

    def save_transcript(self, memo_id: str, transcript: str, model: str) -> None:
        self.connection.execute(
            """
            UPDATE memos SET transcript = ?, transcript_model = ?,
                transcription_error = NULL, transcription_error_at = NULL,
                updated_at = ?
            WHERE memo_id = ?
            """,
            (transcript, model, datetime.now(timezone.utc).isoformat(), memo_id),
        )
        self.connection.commit()

    def save_transcription_error(self, memo_id: str, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            UPDATE memos SET transcription_error = ?, transcription_error_at = ?,
                transcription_attempts = transcription_attempts + 1, updated_at = ?
            WHERE memo_id = ?
            """,
            (error[:4000], now, now, memo_id),
        )
        self.connection.commit()

    def save_classification(self, memo_id: str, status: str, confidence: float, reason: str) -> None:
        self.connection.execute(
            """
            UPDATE memos SET
                journal_status = CASE WHEN status_is_manual = 1 THEN journal_status ELSE ? END,
                journal_confidence = CASE WHEN status_is_manual = 1 THEN journal_confidence ELSE ? END,
                journal_reason = CASE WHEN status_is_manual = 1 THEN journal_reason ELSE ? END,
                updated_at = ?
            WHERE memo_id = ?
            """,
            (status, confidence, reason, datetime.now(timezone.utc).isoformat(), memo_id),
        )
        self.connection.commit()

    def set_manual_status(self, memo_id: str, is_journal: bool) -> None:
        self.connection.execute(
            """
            UPDATE memos SET journal_status = ?, journal_confidence = 1.0,
                journal_reason = 'User override', status_is_manual = 1, updated_at = ?
            WHERE memo_id = ?
            """,
            (
                "journal" if is_journal else "not_journal",
                datetime.now(timezone.utc).isoformat(),
                memo_id,
            ),
        )
        self.connection.commit()

    def mark_analyzed(self, memo_id: str, analyzed: bool, note: str | None = None) -> None:
        analyzed_at = datetime.now(timezone.utc).isoformat() if analyzed else None
        self.connection.execute(
            "UPDATE memos SET analyzed_at = ?, analysis_note = ?, updated_at = ? WHERE memo_id = ?",
            (analyzed_at, note if analyzed else None, datetime.now(timezone.utc).isoformat(), memo_id),
        )
        self.connection.commit()

    @staticmethod
    def _row_to_memo(row: sqlite3.Row) -> Memo:
        return Memo(
            memo_id=row["memo_id"],
            path=Path(row["path"]),
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            title=row["title"],
            duration_seconds=row["duration_seconds"],
            transcript=row["transcript"],
            transcription_error=row["transcription_error"],
            transcription_error_at=(
                datetime.fromisoformat(row["transcription_error_at"])
                if row["transcription_error_at"]
                else None
            ),
            transcription_attempts=row["transcription_attempts"] or 0,
            journal_status=row["journal_status"],
            journal_confidence=row["journal_confidence"],
            journal_reason=row["journal_reason"],
            analyzed_at=datetime.fromisoformat(row["analyzed_at"]) if row["analyzed_at"] else None,
            analysis_note=row["analysis_note"],
        )
