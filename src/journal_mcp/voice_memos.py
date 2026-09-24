from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Memo


AUDIO_EXTENSIONS = {".m4a", ".mp4", ".caf", ".wav", ".aac", ".mp3"}


def _raise_scan_error(error: OSError) -> None:
    if isinstance(error, PermissionError):
        raise PermissionError(
            "macOS denied access to the Voice Memos recordings folder. "
            "Grant Full Disk Access to the Journal tunnel process."
        ) from error
    raise error


def candidate_recordings_dirs() -> list[Path]:
    home = Path.home()
    return [
        home / "Library" / "Group Containers" / "group.com.apple.VoiceMemos.shared" / "Recordings",
        home / "Library" / "Containers" / "com.apple.VoiceMemos" / "Data" / "Library" / "Application Support" / "Recordings",
        home / "Library" / "Application Support" / "com.apple.voicememos" / "Recordings",
    ]


def resolve_recordings_dir(override: Path | None = None) -> Path:
    candidates = [override] if override else candidate_recordings_dirs()
    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_dir():
            return candidate
    rendered = "\n".join(f"- {path}" for path in candidates if path)
    raise FileNotFoundError(
        "Could not locate the macOS Voice Memos recordings directory. Checked:\n"
        f"{rendered}\nSet JOURNAL_VOICE_MEMOS_DIR to override discovery."
    )


def _stable_id(path: Path) -> str:
    stem = path.stem.strip()
    if len(stem) >= 16:
        return stem
    stat = path.stat()
    material = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()
    return hashlib.sha256(material).hexdigest()[:24]


def _core_data_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    # Core Data commonly stores seconds since 2001-01-01.
    if 0 < seconds < 1_200_000_000:
        seconds += 978_307_200
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _metadata_from_databases(root: Path) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    databases = list(root.parent.glob("*.db")) + list(root.glob("*.db"))
    for database in databases:
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            for table in tables:
                if "record" not in table.lower():
                    continue
                columns = [
                    row[1]
                    for row in connection.execute(f'PRAGMA table_info("{table}")')
                ]
                upper = {column.upper(): column for column in columns}
                id_col = next(
                    (upper[key] for key in ("ZUNIQUEID", "ZIDENTIFIER", "ZUUID") if key in upper),
                    None,
                )
                path_col = next(
                    (upper[key] for key in ("ZPATH", "ZFILENAME", "ZURL") if key in upper),
                    None,
                )
                if not id_col and not path_col:
                    continue
                title_col = next(
                    (upper[key] for key in ("ZCUSTOMLABEL", "ZTITLE", "ZLABEL") if key in upper),
                    None,
                )
                date_col = next(
                    (upper[key] for key in ("ZDATE", "ZCREATIONDATE", "ZSTARTDATE") if key in upper),
                    None,
                )
                duration_col = next(
                    (upper[key] for key in ("ZDURATION", "ZLENGTH") if key in upper),
                    None,
                )
                selected = [column for column in (id_col, path_col, title_col, date_col, duration_col) if column]
                quoted = ", ".join(f'"{column}"' for column in selected)
                try:
                    rows = connection.execute(f'SELECT {quoted} FROM "{table}"')
                except sqlite3.Error:
                    continue
                for row in rows:
                    record = dict(zip(selected, row, strict=False))
                    keys = set()
                    for column in (id_col, path_col):
                        if record.get(column):
                            value = str(record[column])
                            keys.update((value, Path(value).stem, Path(value).name))
                    value = {
                        "title": str(record[title_col]) if title_col and record.get(title_col) else None,
                        "recorded_at": _core_data_datetime(record.get(date_col)) if date_col else None,
                        "duration_seconds": float(record[duration_col]) if duration_col and record.get(duration_col) else None,
                    }
                    for key in keys:
                        metadata[key.lower()] = value
        except sqlite3.Error:
            pass
        finally:
            connection.close()
    return metadata


def scan_voice_memos(override: Path | None = None, limit: int | None = None) -> list[Memo]:
    root = resolve_recordings_dir(override)
    metadata = _metadata_from_databases(root)
    files = [
        Path(directory) / name
        for directory, _, names in os.walk(root, onerror=_raise_scan_error)
        for name in names
        if Path(name).suffix.lower() in AUDIO_EXTENSIONS
    ]
    files.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    if limit is not None:
        files = files[: max(0, limit)]

    memos: list[Memo] = []
    for path in files:
        stat = path.stat()
        memo_id = _stable_id(path)
        details = (
            metadata.get(memo_id.lower())
            or metadata.get(path.name.lower())
            or metadata.get(path.stem.lower())
            or {}
        )
        memos.append(
            Memo(
                memo_id=memo_id,
                path=path,
                recorded_at=details.get("recorded_at")
                or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                title=details.get("title") or (path.stem if not path.stem.isupper() else None),
                duration_seconds=details.get("duration_seconds"),
            )
        )
    return memos
