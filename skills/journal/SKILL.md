---
name: journal
description: Retrieve, identify, search, and reflect on the user's Apple Voice Memo journal entries through the Journal plugin. Use when the user invokes @Journal or asks about a recent, latest, dated, topical, analyzed, or unanalyzed spoken journal entry; asks for help understanding a voice journal; or corrects whether a memo is a journal entry.
---

# Journal

Use the Journal tools to retrieve the relevant spoken entry before reflecting on it.

## Resolve the entry

1. For “latest” without a topic, call `find_journal_entries` without a query.
2. For “today” or another calendar date, call `find_journal_entries` with `recorded_on` in
   `YYYY-MM-DD` format. Do not pass date words such as “today” as a topic query.
3. For “latest about X,” call `find_journal_entries` with X as the query.
4. Analyzed state is metadata only. Never exclude an entry merely because it was discussed. If the
   user explicitly asks for an unanalyzed entry, request a larger shortlist when necessary and use
   the returned analyzed metadata to choose one.
5. If one recording fails transcription, report it only when relevant and continue with other
   candidates. Never let a broken historical recording block a dated or latest-entry result.
6. If no good result appears, use a larger shortlist or transcription budget only for genuinely
   broad or topical searches.
7. Treat `uncertain` classifications as candidates. Briefly distinguish close candidates or ask the user when ambiguity would materially change the response.
8. Respect manual journal/non-journal status without second-guessing it.

## Archive backfill

When the user asks to start backfill, first call `journal_backfill_status`. If it is already
starting, running, or completed, report that state without calling Start again. Only call
`start_journal_backfill` when no job is active and the user explicitly asks to begin, since it
uploads old recordings and can incur API usage. A completed job needs a new explicit request to
scan newly arrived recordings or retry known failures. It runs in the background and resumes
from cached transcripts. Repeat the returned `summary` in the chat. For a progress request, call
`journal_backfill_status` and repeat the returned `summary`; include the current entry or recent
failures only when useful. Use `stop_journal_backfill` when the user asks to pause or stop it.
Do not imply that the plugin can post unsolicited updates after the current ChatGPT turn ends.

## Reflect

Reflection is opt-in. Use it when the user asks to reflect on, unpack, understand, structure, or get an opinion about an entry. Do not add reflection to a lookup, list, preview, or transcript-only request, and skip it whenever the user asks not to analyze the entry.

Treat the transcript as a spoken journal entry. Help the user understand what they are feeling and thinking and structure their thoughts. Quote sparingly. Help them understand the entry rather than merely summarize it. Identify the central concern, emotional logic, recurring pattern, tension or contradiction, and the most useful question or next step. Distinguish observation from inference. Do not medicalize ordinary uncertainty or force every reflection into productivity advice.

After a requested reflection, use the entry's recording date and central theme to give the chat a concise title in the format `MMM D, YYYY — Short specific description`, such as `Jan 5, 2026 — Learning to Trust Myself`. Use the entry's date, not today's date. If the host supports renaming the current chat, set that title; otherwise present the exact text as a suggested chat title without implying the chat was renamed. Title generation is opt-in: omit it when the user asks for no title.

## Track completion

After delivering a substantive reflection, call `mark_journal_entry_analyzed` with a short note describing what was unpacked. Do not mark an entry after only finding, listing, previewing, or transcribing it. If the user wants to revisit an entry, retrieve it even when already analyzed. Undo analyzed state when the user says the discussion was incomplete or selected the wrong memo.

## Corrections

When the user says a memo is or is not a journal entry, call `set_journal_entry_status`. User overrides take precedence over automatic classification.
