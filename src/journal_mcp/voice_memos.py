from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Memo


AUDIO_EXTENSIONS = {".m4a", ".mp4", ".caf", ".wav", ".aac", ".mp3", ".qta"}


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
                # CloudKit's encrypted title field can be text in the local DB.
                # New recordings may keep only a timestamp in ZCUSTOMLABEL.
                title_cols = [
                    upper[key]
                    for key in ("ZENCRYPTEDTITLE", "ZCUSTOMLABEL", "ZTITLE", "ZLABEL")
                    if key in upper
                ]
                date_col = next(
                    (upper[key] for key in ("ZDATE", "ZCREATIONDATE", "ZSTARTDATE") if key in upper),
                    None,
                )
                duration_col = next(
                    (upper[key] for key in ("ZDURATION", "ZLENGTH") if key in upper),
                    None,
                )
                selected = [column for column in (id_col, path_col, *title_cols, date_col, duration_col) if column]
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
                        "title": next(
                            (record[column] for column in title_cols
                             if isinstance(record.get(column), str) and record[column].strip()),
                            None,
                        ),
                        "recorded_at": _core_data_datetime(record.get(date_col)) if date_col else None,
                        "duration_seconds": float(record[duration_col]) if duration_col and record.get(duration_col) else None,
                        "source_path": record.get(path_col) if path_col else None,
                        "identifier": record.get(id_col) if id_col else None,
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
    memos: dict[str, Memo] = {}
    priorities: dict[str, int] = {}
    for path in files:
        # ApplicationAssets contains playback caches and intermediate tracks.
        # A composed asset can be a fallback, but is not a separate recording.
        cached_asset = "ApplicationAssets" in path.relative_to(root).parts
        if cached_asset and path.stem != "composedAsset":
            continue
        stat = path.stat()
        memo_id = _stable_id(path)
        details = (
            metadata.get(memo_id.lower())
            or metadata.get(path.name.lower())
            or metadata.get(path.stem.lower())
            or (metadata.get(path.parent.name.lower()) if cached_asset else None)
            or {}
        )
        source_path = Path(details["source_path"]) if details.get("source_path") else None
        if source_path is not None and not source_path.is_absolute():
            source_path = root / source_path
        if cached_asset:
            if source_path is None:
                continue
            if source_path.exists() or len(source_path.stem) >= 16:
                memo_id = _stable_id(source_path)
            else:
                memo_id = str(details.get("identifier") or path.parent.name)
        priority = 0 if path == source_path else (2 if cached_asset else 1)
        if memo_id in priorities and priorities[memo_id] <= priority:
            continue
        priorities[memo_id] = priority
        memos[memo_id] = Memo(
            memo_id=memo_id,
            path=path,
            recorded_at=details.get("recorded_at")
            or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            title=details.get("title") or (path.stem if not path.stem.isupper() else None),
            duration_seconds=details.get("duration_seconds"),
        )
    # iCloud downloads and playback can update file mtimes long after recording.
    recent = sorted(memos.values(), key=lambda memo: memo.recorded_at, reverse=True)
    return recent if limit is None else recent[: max(0, limit)]
