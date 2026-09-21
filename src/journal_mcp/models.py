from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
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
    analysis_note: str | None = None

    def public_dict(
        self,
        *,
        include_path: bool = False,
        include_transcript: bool = True,
        excerpt_chars: int = 280,
        excerpt_query: str | None = None,
    ) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path) if include_path else None
        data["recorded_at"] = self.recorded_at.astimezone(timezone.utc).isoformat()
        data["analyzed_at"] = (
            self.analyzed_at.astimezone(timezone.utc).isoformat()
            if self.analyzed_at
            else None
        )
        if not include_transcript:
            transcript = data.pop("transcript")
            data["transcript_excerpt"] = self._excerpt(
                transcript, max(80, excerpt_chars), excerpt_query
            )
        return data

    @staticmethod
    def _excerpt(text: str | None, length: int, query: str | None) -> str | None:
        if not text or len(text) <= length:
            return text

        match_at: int | None = None
        if query:
            lowered = text.lower()
            for token in re.findall(r"[a-z0-9]+", query.lower()):
                if len(token) > 1:
                    position = lowered.find(token)
                    if position >= 0 and (match_at is None or position < match_at):
                        match_at = position

        start = 0 if match_at is None else max(0, match_at - length // 3)
        end = min(len(text), start + length)
        start = max(0, end - length)
        excerpt = text[start:end].strip()
        return f"{'…' if start else ''}{excerpt}{'…' if end < len(text) else ''}"
