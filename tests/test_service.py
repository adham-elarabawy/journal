from datetime import datetime, timedelta, timezone
from pathlib import Path

from journal_mcp.config import Settings
from journal_mcp.models import Memo
from journal_mcp.service import JournalService


def test_find_latest_unanalyzed_entry_about_topic(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    memos = [
        Memo("old", tmp_path / "old.m4a", now - timedelta(days=2), title="Older thought", duration_seconds=100),
        Memo("new", tmp_path / "new.m4a", now, title="Crossroads", duration_seconds=130),
        Memo("list", tmp_path / "list.m4a", now - timedelta(hours=1), title="Groceries", duration_seconds=8),
    ]
    transcripts = {
        "old.m4a": "I feel unsure about moving and I want to understand why. " * 6,
        "new.m4a": "I have been thinking about moving and which neighborhood would fit. " * 8,
        "list.m4a": "Grocery list: eggs and milk.",
    }

    def scanner(_override, limit=None):
        return memos[:limit]

    def transcriber(path, _model):
        return transcripts[path.name]

    service = JournalService(
        Settings(None, tmp_path / "data", "test-model"),
        scanner=scanner,
        transcriber=transcriber,
    )
    results = service.find_entries(query="moving", transcription_budget=3)
    assert results[0].memo_id == "new"

    service.store.mark_analyzed("new", True, "Discussed moving tradeoffs")
    results = service.find_entries(query="moving", transcription_budget=0)
    assert [memo.memo_id for memo in results] == ["old"]


def test_manual_status_survives_reclassification(tmp_path: Path) -> None:
    memo = Memo(
        "memo", tmp_path / "memo.m4a", datetime.now(timezone.utc), duration_seconds=120
    )

    service = JournalService(
        Settings(None, tmp_path / "data", "test-model"),
        scanner=lambda _override, limit=None: [memo],
        transcriber=lambda _path, _model: "Grocery list: eggs and milk.",
    )
    service.sync()
    service.store.set_manual_status("memo", True)
    service.ensure_transcript(service.store.get("memo"))
    assert service.store.get("memo").journal_status == "journal"


def test_preview_hides_full_transcript_and_exposes_analysis_note(tmp_path: Path) -> None:
    memo = Memo(
        "memo", tmp_path / "memo.m4a", datetime.now(timezone.utc), duration_seconds=120
    )
    service = JournalService(
        Settings(None, tmp_path / "data", "test-model"),
        scanner=lambda _override, limit=None: [memo],
        transcriber=lambda _path, _model: "I have been thinking about moving. " * 20,
    )
    result = service.find_entries(transcription_budget=1)[0]
    service.store.mark_analyzed(result.memo_id, True, "Discussed the tradeoffs around moving")
    refreshed = service.store.get(result.memo_id)
    preview = refreshed.public_dict(include_transcript=False)

    assert "transcript" not in preview
    assert preview["transcript_excerpt"].endswith("…")
    assert preview["analysis_note"] == "Discussed the tradeoffs around moving"
