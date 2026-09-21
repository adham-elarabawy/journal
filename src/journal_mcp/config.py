from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    recordings_dir: Path | None
    data_dir: Path
    transcription_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        recordings = os.getenv("JOURNAL_VOICE_MEMOS_DIR")
        data = os.getenv("JOURNAL_DATA_DIR")
        return cls(
            recordings_dir=Path(recordings).expanduser() if recordings else None,
            data_dir=(
                Path(data).expanduser()
                if data
                else Path.home() / "Library" / "Application Support" / "Journal"
            ),
            transcription_model=os.getenv(
                "JOURNAL_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"
            ),
        )

