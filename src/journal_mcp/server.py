from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .backfill import backfill_manager
from .config import Settings
from .service import JournalService


mcp = FastMCP(
    "Journal",
    instructions=(
        "Use these tools to find and retrieve the user's Apple Voice Memo journal entries. "
        "Analyzed state is metadata only; never exclude an entry merely because it was discussed. "
        "Choose entries by the user's requested date, recency, and topic. "
        "Low-confidence classifications are candidates, not facts. Mark an entry analyzed only after "
        "a substantive reflection has been delivered, never after a preview or lookup alone. "
        "When the user asks to reflect on, unpack, understand, structure, or get an opinion about an "
        "entry, treat it as a spoken journal entry: help the user understand what they are feeling and "
        "thinking and structure their thoughts. End with a suggested chat title in the format "
        "'YYYY-MM-DD — Short specific theme'. Reflection and title generation are opt-in behaviors: "
        "do not add them to a lookup, list, or transcript-only request, and omit either when the user "
        "asks not to receive it. For dated requests, pass recorded_on so unrelated older memos are "
        "never transcribed. A failed recording must not block another result. When the user "
        "explicitly asks to start archive backfill, call start_journal_backfill directly; do not "
        "substitute journal_status or journal_backfill_status. When starting or checking archive "
        "backfill, repeat the returned summary in the chat response."
    ),
)


def service() -> JournalService:
    return JournalService(Settings.from_env())


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE_LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


@mcp.tool(annotations=READ_ONLY)
def journal_status() -> dict[str, Any]:
    """Check whether Voice Memos can be found and report local journal index counts."""
    journal = service()
    memos = journal.sync(limit=200)
    return {
        "recordings_found": len(memos),
        "transcribed": sum(memo.transcript is not None for memo in memos),
        "journal_entries": sum(memo.journal_status == "journal" for memo in memos),
        "unanalyzed_journal_entries": sum(
            memo.journal_status == "journal" and not memo.analyzed_at for memo in memos
        ),
        "data_file": str(journal.store.path),
        "backfill": backfill_manager.status(journal.settings),
    }


@mcp.tool(annotations=READ_ONLY)
def find_journal_entries(
    query: str | None = None,
    limit: int = 1,
    scan_limit: int = 30,
    transcription_budget: int = 1,
    recorded_on: str | None = None,
    retry_failed: bool = False,
) -> dict[str, Any]:
    """Find the latest journal-like Voice Memos, optionally about a topic.

    Use query for requests such as "latest entry about a difficult decision". For "today" or
    another calendar date, pass recorded_on in YYYY-MM-DD format instead of putting the date in
    query. Analyzed entries
    remain eligible and expose their analyzed state as metadata. A latest-entry lookup defaults
    to one result and at most one new transcription. Increase the budget only for broader topical
    searches. Failed recordings are reported and skipped so they cannot block another result.
    Results contain metadata and short excerpts; call get_journal_entry for the full transcript.
    """
    journal = service()
    entries = journal.find_entries(
        query=query,
        limit=max(1, min(limit, 20)),
        scan_limit=max(1, min(scan_limit, 200)),
        transcription_budget=max(0, min(transcription_budget, 30)),
        recorded_on=recorded_on,
        retry_failed=retry_failed,
    )
    return {
        "entries": [
            entry.public_dict(
                include_transcript=False,
                excerpt_chars=2000,
                excerpt_query=query,
            )
            for entry in entries
        ],
        "classification_note": (
            "'uncertain' entries need conversational judgment. User overrides always win."
        ),
        "transcription_failures": journal.last_find_failures,
    }


@mcp.tool(annotations=WRITE_LOCAL)
def start_journal_backfill(retry_failed: bool = False) -> dict[str, Any]:
    """Start resumable archive transcription in the background and return immediately.

    This uploads previously untranscribed Voice Memos to the configured OpenAI transcription
    model and may incur API usage. Call only when the user explicitly asks to start. Previously
    failed recordings are skipped unless retry_failed is true. Repeat the returned summary in chat.
    """
    return backfill_manager.start(Settings.from_env(), retry_failed=retry_failed)


@mcp.tool(annotations=READ_ONLY)
def journal_backfill_status() -> dict[str, Any]:
    """Report archive transcription progress. Repeat the returned summary in chat."""
    return backfill_manager.status(Settings.from_env())


@mcp.tool(annotations=WRITE_LOCAL)
def stop_journal_backfill() -> dict[str, Any]:
    """Ask the background archive transcription job to pause after its current memo."""
    return backfill_manager.stop(Settings.from_env())


@mcp.tool(annotations=READ_ONLY)
def get_journal_entry(memo_id: str) -> dict[str, Any]:
    """Retrieve one memo by stable ID and transcribe it if needed."""
    journal = service()
    journal.sync(limit=500)
    memo = journal.store.get(memo_id)
    if memo is None:
        raise ValueError(f"Unknown memo_id: {memo_id}")
    memo = journal.ensure_transcript(memo)
    return memo.public_dict()


@mcp.tool(annotations=WRITE_LOCAL)
def set_journal_entry_status(memo_id: str, is_journal: bool) -> dict[str, Any]:
    """Override whether a Voice Memo is a journal entry. This is reversible."""
    journal = service()
    journal.store.set_manual_status(memo_id, is_journal)
    memo = journal.store.get(memo_id)
    if memo is None:
        raise ValueError(f"Unknown memo_id: {memo_id}")
    return memo.public_dict(include_transcript=False)


@mcp.tool(annotations=WRITE_LOCAL)
def mark_journal_entry_analyzed(
    memo_id: str, analyzed: bool = True, note: str | None = None
) -> dict[str, Any]:
    """Mark or unmark an entry as substantively analyzed in ChatGPT.

    Call with analyzed=true only after the assistant has delivered a substantive reflection,
    not merely after finding, previewing, or transcribing the entry.
    """
    journal = service()
    journal.store.mark_analyzed(memo_id, analyzed, note)
    memo = journal.store.get(memo_id)
    if memo is None:
        raise ValueError(f"Unknown memo_id: {memo_id}")
    return memo.public_dict(include_transcript=False)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
