from pathlib import Path
import os
import sqlite3
from datetime import datetime, timezone

import pytest

from journal_mcp import voice_memos


def test_scan_reports_permission_error_instead_of_empty_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied_walk(_root: Path, *, onerror):
        onerror(PermissionError("Operation not permitted"))
        yield from ()

    monkeypatch.setattr(voice_memos.os, "walk", denied_walk)

    with pytest.raises(PermissionError, match="Full Disk Access"):
        voice_memos.scan_voice_memos(tmp_path)


def test_qta_metadata_order_and_playback_cache_deduplication(tmp_path: Path) -> None:
    older = tmp_path / "20260101 120000-AAAAAAAA.m4a"
    newer = tmp_path / "20260923 120000-BBBBBBBB.qta"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    os.utime(older, (1_800_000_000, 1_800_000_000))
    os.utime(newer, (1_700_000_000, 1_700_000_000))
    cache = tmp_path / "ApplicationAssets" / "recording-uuid" / "composedAsset.qta"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"cached")
    with sqlite3.connect(tmp_path / "CloudRecordings.db") as db:
        db.execute("CREATE TABLE ZCLOUDRECORDING (ZUNIQUEID TEXT, ZPATH TEXT, ZDATE REAL, ZCUSTOMLABEL TEXT, ZENCRYPTEDTITLE TEXT, ZDURATION REAL)")
        db.executemany("INSERT INTO ZCLOUDRECORDING VALUES (?, ?, ?, ?, ?, ?)", [
            ("old-uuid", older.name, 788_961_600, "Older memo", None, 100),
            ("recording-uuid", newer.name, 811_857_600, "2026-09-23T12:00:00Z", "A recent journal", 975),
        ])

    memos = voice_memos.scan_voice_memos(tmp_path)
    assert len(memos) == 2
    assert memos[0].path == newer
    assert memos[0].memo_id == newer.stem
    assert memos[0].title == "A recent journal"
    assert memos[0].recorded_at == datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
    assert memos[0].duration_seconds == 975
    assert voice_memos.scan_voice_memos(tmp_path, limit=1)[0].path == newer

    newer.unlink()
    fallback = voice_memos.scan_voice_memos(tmp_path, limit=1)[0]
    assert fallback.path == cache
    assert fallback.memo_id == newer.stem
    assert fallback.title == "A recent journal"
