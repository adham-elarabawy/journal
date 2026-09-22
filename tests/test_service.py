from datetime import datetime, timedelta, timezone
from pathlib import Path

from journal_mcp.config import Settings
from journal_mcp.models import Memo
from journal_mcp.service import JournalService


def test_analyzed_entry_remains_eligible_for_topic_search(tmp_path: Path) -> None:
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
    assert [memo.memo_id for memo in results] == ["new"]
    assert results[0].analyzed_at is not None


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
    preview = refreshed.public_dict(include_transcript=False, excerpt_chars=2000)

    assert "transcript" not in preview
    assert preview["transcript_excerpt"].startswith("I have been thinking about moving.")
    assert preview["analysis_note"] == "Discussed the tradeoffs around moving"


def test_topic_preview_is_long_and_centered_on_match(tmp_path: Path) -> None:
    transcript = f"{'Opening context. ' * 200}moving feels like the important decision{' Later context.' * 200}"
    memo = Memo(
        "memo", tmp_path / "memo.m4a", datetime.now(timezone.utc), transcript=transcript
    )

    preview = memo.public_dict(
        include_transcript=False,
        excerpt_chars=2000,
        excerpt_query="moving",
    )["transcript_excerpt"]

    assert "moving feels like the important decision" in preview
    assert 1900 <= len(preview) <= 2002
    assert preview.startswith("…")
    assert preview.endswith("…")


def test_silent_recording_is_cached_and_not_retranscribed(tmp_path: Path) -> None:
    memo = Memo("silent", tmp_path / "silent.m4a", datetime.now(timezone.utc), duration_seconds=3)
    calls = 0

    def transcriber(_path, _model):
        nonlocal calls
        calls += 1
        return ""

    service = JournalService(
        Settings(None, tmp_path / "data", "test-model"),
        scanner=lambda _override, limit=None: [memo],
        transcriber=transcriber,
    )
    service.find_entries(transcription_budget=1)
    service.find_entries(transcription_budget=1)

    stored = service.store.get("silent")
    assert calls == 1
    assert stored.transcript == ""
    assert stored.journal_status == "not_journal"


def test_latest_lookup_stops_after_first_journal_entry(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    memos = [
        Memo(str(index), tmp_path / f"{index}.m4a", now - timedelta(hours=index))
        for index in range(3)
    ]
    calls = []

    def transcriber(path, _model):
        calls.append(path.name)
        return "I have been reflecting on this decision and how it affects my life. " * 5

    service = JournalService(
        Settings(None, tmp_path / "data", "test-model"),
        scanner=lambda _override, limit=None: memos[:limit],
        transcriber=transcriber,
    )

    results = service.find_entries()

    assert [memo.memo_id for memo in results] == ["0"]
    assert calls == ["0.m4a"]


def test_latest_can_reuse_analyzed_entry_without_transcribing_older_memos(
    tmp_path: Path,
) -> None:
    now = datetime.now(timezone.utc)
    latest = Memo(
        "latest",
        tmp_path / "latest.m4a",
        now,
        transcript="I have been thinking about a difficult decision. " * 5,
        journal_status="journal",
    )
    older = Memo("older", tmp_path / "older.m4a", now - timedelta(days=1))
    calls = []

    service = JournalService(
        Settings(None, tmp_path / "data", "test-model"),
        scanner=lambda _override, limit=None: [latest, older][:limit],
        transcriber=lambda path, _model: calls.append(path.name) or "unexpected",
    )
    service.sync()
    service.store.save_transcript(latest.memo_id, latest.transcript or "", "test-model")
    service.store.save_classification(latest.memo_id, "journal", 0.9, "Reflective entry")
    service.store.mark_analyzed(latest.memo_id, True, "Previously discussed")

    results = service.find_entries(transcription_budget=0)

    assert [memo.memo_id for memo in results] == ["latest"]
    assert calls == []


def test_dated_lookup_never_transcribes_unrelated_older_memo(tmp_path: Path) -> None:
    today = datetime(2026, 9, 21, 18, tzinfo=timezone.utc)
    current = Memo(
        "today",
        tmp_path / "today.m4a",
        today,
        transcript="I am reflecting on what happened today. " * 5,
        journal_status="journal",
    )
    older = Memo("older", tmp_path / "older.m4a", today - timedelta(days=1))
    calls = []
    service = JournalService(
        Settings(None, tmp_path / "data", "test-model"),
        scanner=lambda _override, limit=None: [current, older][:limit],
        transcriber=lambda path, _model: calls.append(path.name) or "unexpected",
    )
    service.sync()
    service.store.save_transcript(current.memo_id, current.transcript or "", "test-model")
    service.store.save_classification(current.memo_id, "journal", 0.9, "Reflective entry")

    results = service.find_entries(recorded_on="2026-09-21", transcription_budget=10)

    assert [memo.memo_id for memo in results] == ["today"]
    assert calls == []


def test_failed_historical_recording_does_not_abort_search(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    matching = Memo(
        "matching",
        tmp_path / "matching.m4a",
        now,
        transcript="I keep thinking about moving and what I really want. " * 5,
        journal_status="journal",
    )
    broken = Memo("broken", tmp_path / "broken.m4a", now - timedelta(days=1))

    def transcriber(path, _model):
        if path.name == "broken.m4a":
            raise RuntimeError("corrupted or unsupported")
        return "unexpected"

    service = JournalService(
        Settings(None, tmp_path / "data", "test-model"),
        scanner=lambda _override, limit=None: [matching, broken][:limit],
        transcriber=transcriber,
    )
    service.sync()
    service.store.save_transcript(matching.memo_id, matching.transcript or "", "test-model")
    service.store.save_classification(matching.memo_id, "journal", 0.9, "Reflective entry")

    results = service.find_entries(query="moving", transcription_budget=1)

    assert [memo.memo_id for memo in results] == ["matching"]
    assert service.last_find_failures[0]["memo_id"] == "broken"
    stored = service.store.get("broken")
    assert stored is not None
    assert stored.transcription_error == "corrupted or unsupported"
    assert stored.transcription_attempts == 1

    service.find_entries(query="moving", transcription_budget=1)
    assert service.store.get("broken").transcription_attempts == 1
