from pathlib import Path

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
