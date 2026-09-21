from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Callable

from .classifier import classify_journal_entry
from .config import Settings
from .models import Memo
from .store import JournalStore
from .transcribe import transcribe_audio
from .voice_memos import scan_voice_memos


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
        self.transcriber = transcriber

    def sync(self, limit: int = 50) -> list[Memo]:
        memos = self.scanner(self.settings.recordings_dir, limit=limit)
        self.store.upsert_scanned(memos)
        return self.store.list_recent(limit)

    def ensure_transcript(self, memo: Memo) -> Memo:
        if memo.transcript:
            return memo
        transcript = self.transcriber(memo.path, self.settings.transcription_model)
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
        include_analyzed: bool = False,
        limit: int = 5,
        scan_limit: int = 30,
        transcription_budget: int = 8,
    ) -> list[Memo]:
        memos = self.sync(limit=scan_limit)
        prepared: list[Memo] = []
        transcribed = 0
        for memo in memos:
            if memo.analyzed_at and not include_analyzed:
                continue
            if not memo.transcript and transcribed < transcription_budget:
                memo = self.ensure_transcript(memo)
                transcribed += 1
            if memo.transcript and memo.journal_status in {"journal", "uncertain", "unknown"}:
                prepared.append(memo)

        if query:
            prepared.sort(key=lambda memo: self._search_score(query, memo), reverse=True)
            prepared = [memo for memo in prepared if self._search_score(query, memo) > 0]
        else:
            prepared.sort(key=lambda memo: memo.recorded_at, reverse=True)
        return prepared[:limit]

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

