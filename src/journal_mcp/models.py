from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Memo:
    memo_id: str
    path: Path
    recorded_at: datetime
    title: str | None = None
    duration_seconds: float | None = None
    transcript: str | None = None
    journal_status: str = "unknown"
    journal_confidence: float | None = None
    journal_reason: str | None = None
    analyzed_at: datetime | None = None

    def public_dict(self, include_path: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path) if include_path else None
        data["recorded_at"] = self.recorded_at.astimezone(timezone.utc).isoformat()
        data["analyzed_at"] = (
            self.analyzed_at.astimezone(timezone.utc).isoformat()
            if self.analyzed_at
            else None
        )
        return data

