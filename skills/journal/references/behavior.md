# Behavior examples

- “Help me understand my latest journal entry.” Retrieve the newest high-confidence or plausible journal entry regardless of analyzed state, reflect on it, suggest a title such as `2026-09-21 — Choosing between stability and change`, then mark it analyzed.
- “Get today’s journal.” Pass today as `recorded_on`; do not scan or transcribe unrelated older recordings.
- “Show me the transcript only—no analysis or title.” Retrieve the entry and return the transcript without reflection or title generation.
- “Find my latest entry about moving and help me weigh the tradeoffs I mentioned.” Search for moving and related tradeoff language. Prefer the latest strong topical match, then retrieve its full transcript before reflecting.
- “That grocery memo is not a journal entry.” Save a manual non-journal override.
- “We already discussed that one; show me an entry we have not discussed.” Mark it analyzed, request a larger shortlist if needed, and choose the next relevant entry whose metadata is unanalyzed.
- “Compare what I said this week about feeling overwhelmed with my previous entry on the same topic.” Retrieve both relevant entries, including an analyzed entry when needed for the comparison.
- “Backfill my older memos.” Start the background job, immediately state its returned progress summary, and mention that the user can ask for status in this chat.
- “How is the backfill going?” Check status and put its concise summary directly in the chat.
