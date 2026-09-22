from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .service import JournalService


class BackfillManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, settings: Settings, *, retry_failed: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                pass
            else:
                self._stop.clear()
                self._write_state(
                    settings,
                    {
                        "status": "starting",
                        "completed": 0,
                        "target_count": 0,
                        "failed": 0,
                        "remaining": 0,
                        "current_entry": None,
                        "started_at": self._now(),
                        "updated_at": self._now(),
                    },
                )
                self._thread = threading.Thread(
                    target=self._run,
                    args=(settings, retry_failed),
                    name="journal-backfill",
                    daemon=True,
                )
                self._thread.start()
        return self.status(settings)

    def stop(self, settings: Settings) -> dict[str, Any]:
        self._stop.set()
        state = self._read_state(settings)
        if state.get("status") == "running":
            state["status"] = "stopping"
            state["updated_at"] = self._now()
            self._write_state(settings, state)
        return self._with_summary(state)

    def status(self, settings: Settings) -> dict[str, Any]:
        state = self._read_state(settings)
        with self._lock:
            alive = bool(self._thread and self._thread.is_alive())
        if state.get("status") in {"running", "stopping"} and not alive:
            state["status"] = "interrupted"
            state["updated_at"] = self._now()
            self._write_state(settings, state)
        return self._with_summary(state)

    def _run(self, settings: Settings, retry_failed: bool) -> None:
        journal = JournalService(settings)
        try:
            journal.sync(limit=500)
            memos = journal.store.list_recent(10_000)
            pending = [
                memo
                for memo in memos
                if memo.transcript is None
                and (retry_failed or not memo.transcription_error)
            ]
            skipped_failed = 0
            if not retry_failed:
                skipped_failed = sum(
                    memo.transcript is None and bool(memo.transcription_error)
                    for memo in memos
                )
            state: dict[str, Any] = {
                "status": "running",
                "total_recordings": len(memos),
                "already_transcribed": sum(memo.transcript is not None for memo in memos),
                "target_count": len(pending),
                "attempted": 0,
                "completed": 0,
                "failed": 0,
                "known_failures_skipped": skipped_failed,
                "remaining": len(pending),
                "current_entry": None,
                "failures": [],
                "started_at": self._now(),
                "updated_at": self._now(),
            }
            self._write_state(settings, state)

            for memo in pending:
                if self._stop.is_set():
                    state["status"] = "paused"
                    break
                state["current_entry"] = {
                    "memo_id": memo.memo_id,
                    "recorded_at": memo.recorded_at.isoformat(),
                    "title": memo.title,
                    "duration_seconds": memo.duration_seconds,
                }
                state["updated_at"] = self._now()
                self._write_state(settings, state)
                try:
                    journal.ensure_transcript(memo)
                    state["completed"] += 1
                except Exception as exc:
                    state["failed"] += 1
                    state["failures"] = (
                        state["failures"]
                        + [{"memo_id": memo.memo_id, "error": str(exc)}]
                    )[-10:]
                state["attempted"] += 1
                state["remaining"] = len(pending) - state["attempted"]
                state["updated_at"] = self._now()
                self._write_state(settings, state)
            else:
                state["status"] = "completed"

            state["current_entry"] = None
            state["updated_at"] = self._now()
            self._write_state(settings, state)
        except Exception as exc:
            state = self._read_state(settings)
            state.update(
                {
                    "status": "failed",
                    "fatal_error": str(exc),
                    "current_entry": None,
                    "updated_at": self._now(),
                }
            )
            self._write_state(settings, state)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _state_path(settings: Settings) -> Path:
        return settings.data_dir / "backfill-status.json"

    def _read_state(self, settings: Settings) -> dict[str, Any]:
        path = self._state_path(settings)
        if not path.exists():
            return {"status": "idle", "updated_at": None}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "unknown", "updated_at": None}

    def _write_state(self, settings: Settings, state: dict[str, Any]) -> None:
        path = self._state_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _with_summary(state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        status = result.get("status", "unknown")
        if status == "idle":
            summary = "Journal archive backfill has not been started."
        else:
            completed = int(result.get("completed", 0))
            target = int(result.get("target_count", 0))
            remaining = int(result.get("remaining", 0))
            failed = int(result.get("failed", 0))
            skipped = int(result.get("known_failures_skipped", 0))
            summary = (
                f"Journal backfill is {status}: {completed}/{target} newly transcribed, "
                f"{remaining} remaining, {failed} failed."
            )
            if skipped:
                summary += f" {skipped} known failures were skipped."
        result["summary"] = summary
        return result


backfill_manager = BackfillManager()
