from datetime import datetime, timedelta, timezone
from pathlib import Path

from journal_mcp import backfill
from journal_mcp.backfill import BackfillManager
from journal_mcp.config import Settings
from journal_mcp.models import Memo


def test_backfill_completes_and_reports_failures(tmp_path: Path, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    memos = [
        Memo("good", tmp_path / "good.m4a", now),
        Memo("bad", tmp_path / "bad.m4a", now - timedelta(days=1)),
    ]

    class FakeStore:
        def list_recent(self, _limit):
            return memos

    class FakeService:
        def __init__(self, _settings):
            self.store = FakeStore()

        def sync(self, limit):
            return memos[:limit]

        def ensure_transcript(self, memo):
            if memo.memo_id == "bad":
                raise RuntimeError("unsupported recording")
            memo.transcript = "A transcript"
            return memo

    monkeypatch.setattr(backfill, "JournalService", FakeService)
    manager = BackfillManager()
    settings = Settings(None, tmp_path / "data", "test-model")

    manager.start(settings)
    assert manager._thread is not None
    manager._thread.join(timeout=2)
    status = manager.status(settings)

    assert status["status"] == "completed"
    assert status["completed"] == 1
    assert status["failed"] == 1
    assert status["remaining"] == 0
    assert "1/2 newly transcribed" in status["summary"]


def test_backfill_stops_after_first_filesystem_permission_error(
    tmp_path: Path, monkeypatch
) -> None:
    now = datetime.now(timezone.utc)
    memos = [
        Memo("first", tmp_path / "first.m4a", now),
        Memo("second", tmp_path / "second.m4a", now - timedelta(days=1)),
    ]
    calls = []

    class FakeStore:
        def list_recent(self, _limit):
            return memos

    class FakeService:
        def __init__(self, _settings):
            self.store = FakeStore()

        def sync(self, limit):
            return memos[:limit]

        def ensure_transcript(self, memo):
            calls.append(memo.memo_id)
            raise PermissionError("Operation not permitted")

    monkeypatch.setattr(backfill, "JournalService", FakeService)
    manager = BackfillManager()
    settings = Settings(None, tmp_path / "data", "test-model")

    manager.start(settings)
    assert manager._thread is not None
    manager._thread.join(timeout=2)
    status = manager.status(settings)

    assert calls == ["first"]
    assert status["status"] == "blocked"
    assert status["failure_type"] == "filesystem_permission"
    assert status["failed"] == 0
    assert status["remaining"] == 2
    assert "blocked by macOS permission" in status["summary"]


def test_starting_summary_does_not_report_zero_target() -> None:
    result = BackfillManager._with_summary(
        {"status": "starting", "completed": 0, "target_count": 0, "remaining": 0}
    )

    assert "counting pending recordings" in result["summary"]
    assert "0/0" not in result["summary"]
