from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Classification:
    status: str
    confidence: float
    reason: str


_REFLECTIVE = (
    "i feel",
    "i've been feeling",
    "i am feeling",
    "i think",
    "i've been thinking",
    "i am thinking",
    "i'm worried",
    "i am worried",
    "i wonder",
    "i want",
    "i don't know",
    "i keep",
    "what i'm struggling",
    "what i am struggling",
    "today i",
    "lately i",
    "right now i",
    "journal",
    "voice diary",
)

_NON_JOURNAL = (
    "meeting notes",
    "call with",
    "interview with",
    "testing testing",
    "grocery list",
    "todo list",
    "to-do list",
    "song idea",
    "lecture",
)


def classify_journal_entry(
    transcript: str | None,
    *,
    duration_seconds: float | None = None,
    title: str | None = None,
) -> Classification:
    """Conservative, explainable first pass; ChatGPT adjudicates ambiguity."""
    if transcript is not None and not transcript.strip():
        return Classification("not_journal", 1.0, "No speech was detected in the recording.")
    text = " ".join(filter(None, (title, transcript))).strip().lower()
    if not text:
        return Classification("unknown", 0.0, "No transcript is available yet.")

    words = re.findall(r"[a-z']+", text)
    reflective_hits = [phrase for phrase in _REFLECTIVE if phrase in text]
    negative_hits = [phrase for phrase in _NON_JOURNAL if phrase in text]
    first_person = sum(words.count(token) for token in ("i", "i'm", "i've", "me", "my"))

    score = 0.18
    reasons: list[str] = []
    if duration_seconds and duration_seconds >= 45:
        score += 0.14
        reasons.append("substantial monologue length")
    elif duration_seconds and duration_seconds < 15:
        score -= 0.18
        reasons.append("very short recording")
    if len(words) >= 90:
        score += 0.12
        reasons.append("extended spoken content")
    if reflective_hits:
        score += min(0.38, 0.13 * len(reflective_hits))
        reasons.append("reflective first-person language")
    if first_person >= 6:
        score += 0.16
        reasons.append("sustained first-person narration")
    elif first_person >= 2:
        score += 0.07
    if negative_hits:
        score -= min(0.45, 0.18 * len(negative_hits))
        reasons.append("task, meeting, or capture-note language")

    score = max(0.0, min(1.0, score))
    if score >= 0.62:
        status = "journal"
    elif score <= 0.12:
        status = "not_journal"
    else:
        status = "uncertain"
    return Classification(status, round(score, 2), ", ".join(reasons) or "Ambiguous content.")
