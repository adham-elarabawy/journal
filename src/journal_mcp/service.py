from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher
from functools import partial
from typing import Callable

from .classifier import classify_journal_entry
from .config import Settings
from .models import Memo
from .store import JournalStore
from .transcribe import transcribe_audio
from .voice_memos import scan_voice_memos


def is_filesystem_permission_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, PermissionError):
            return True
        message = str(current).lower()
        if "operation not permitted" in message or "permission denied" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


class JournalService:
    def __init__(
        self,
        settings: Settings,
        *,
        scanner: Callable[..., list[Memo]] = scan_voice_memos,
        transcriber: Callable[[object, str], str] = transcribe_audio,
    ):
        self.settings = settings
        self.store = JournalStore(settings.data_dir)
        self.scanner = scanner
        self.transcriber = (
            partial(
                transcribe_audio,
                cache_dir=settings.data_dir / "transcription-parts",
            )
            if transcriber is transcribe_audio
            else transcriber
        )
        self.last_find_failures: list[dict[str, object]] = []

    def sync(self, limit: int = 50) -> list[Memo]:
        memos = self.scanner(self.settings.recordings_dir, limit=limit)
        self.store.upsert_scanned(memos)
        return self.store.list_recent(limit)

    def ensure_transcript(self, memo: Memo) -> Memo:
        if memo.transcript is not None:
            return memo
        try:
            transcript = self.transcriber(memo.path, self.settings.transcription_model)
        except Exception as exc:
            if not is_filesystem_permission_error(exc):
                self.store.save_transcription_error(memo.memo_id, str(exc))
            raise
        self.store.save_transcript(memo.memo_id, transcript, self.settings.transcription_model)
        classification = classify_journal_entry(
            transcript, duration_seconds=memo.duration_seconds, title=memo.title
        )
        self.store.save_classification(
            memo.memo_id,
            classification.status,
            classification.confidence,
            classification.reason,
        )
        refreshed = self.store.get(memo.memo_id)
        assert refreshed is not None
        return refreshed

    def find_entries(
        self,
        *,
        query: str | None = None,
        limit: int = 1,
        scan_limit: int = 30,
        transcription_budget: int = 1,
        recorded_on: str | None = None,
        retry_failed: bool = False,
    ) -> list[Memo]:
        memos = self.sync(limit=scan_limit)
        if recorded_on:
            try:
                target_date = date.fromisoformat(recorded_on)
            except ValueError as exc:
                raise ValueError("recorded_on must use YYYY-MM-DD format") from exc
            memos = [
                memo
                for memo in memos
                if memo.recorded_at.astimezone().date() == target_date
            ]
        prepared: list[Memo] = []
        self.last_find_failures = []
        transcribed = 0
        for memo in memos:
            if memo.transcript is None:
                if memo.transcription_error and not retry_failed:
                    self.last_find_failures.append(self._failure_dict(memo))
                    continue
                if transcribed >= transcription_budget:
                    continue
                transcribed += 1
                try:
                    memo = self.ensure_transcript(memo)
                except Exception as exc:
                    failed = self.store.get(memo.memo_id) or memo
                    self.last_find_failures.append(self._failure_dict(failed, str(exc)))
                    continue
            if memo.transcript and memo.journal_status in {"journal", "uncertain", "unknown"}:
                prepared.append(memo)
                if not query and len(prepared) >= limit:
                    break

        if query:
            prepared.sort(key=lambda memo: self._search_score(query, memo), reverse=True)
            prepared = [memo for memo in prepared if self._search_score(query, memo) > 0]
        else:
            prepared.sort(key=lambda memo: memo.recorded_at, reverse=True)
        return prepared[:limit]

    @staticmethod
    def _failure_dict(memo: Memo, error: str | None = None) -> dict[str, object]:
        return {
            "memo_id": memo.memo_id,
            "recorded_at": memo.recorded_at.isoformat(),
            "title": memo.title,
            "error": error or memo.transcription_error or "Unknown transcription error",
            "attempts": memo.transcription_attempts,
        }

    @staticmethod
    def _search_score(query: str, memo: Memo) -> float:
        haystack = " ".join(filter(None, (memo.title, memo.transcript))).lower()
        tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 1]
        if not tokens:
            return 0.0
        exact = sum(1.0 for token in tokens if token in haystack)
        fuzzy = sum(
            max((SequenceMatcher(None, token, word).ratio() for word in haystack.split()), default=0.0)
            for token in tokens
        )
        recency_bonus = memo.recorded_at.timestamp() / 1e11
        return exact * 2.0 + fuzzy + recency_bonus
