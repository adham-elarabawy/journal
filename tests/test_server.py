from datetime import datetime, timezone
from pathlib import Path

from journal_mcp import server
from journal_mcp.config import Settings
from journal_mcp.models import Memo


def test_status_does_not_report_cached_entries_as_fresh_recordings(
    tmp_path: Path, monkeypatch
) -> None:
    cached = Memo("cached", tmp_path / "cached.m4a", datetime.now(timezone.utc))

    class FakeStore:
        def list_recent(self, _limit):
            return [cached]

        path = tmp_path / "journal.sqlite3"

    class FakeService:
        settings = Settings(None, tmp_path, "test-model")
        store = FakeStore()

        def sync(self, limit):
            raise PermissionError("Operation not permitted")

    monkeypatch.setattr(server, "service", FakeService)
    monkeypatch.setattr(server.backfill_manager, "status", lambda _settings: {})

    result = server.journal_status()

    assert result["recordings_found"] is None
    assert result["indexed_recordings"] == 1
    assert "macOS denied access" in result["discovery_error"]
