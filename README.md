# Journal

Journal is a private, local-first ChatGPT plugin for reflecting on Apple Voice Memos. It reads iCloud-synced recordings from the Mac, transcribes only the memos needed for a request, identifies likely journal entries, and remembers which entries have already been discussed.

Example prompts:

- `@Journal help me understand my latest journal entry.`
- `@Journal give me your opinion about my latest entry about the company.`
- `@Journal find the entry from last week where I was worried about hiring.`

## Design

- Voice Memos remains the source of truth.
- Audio is read locally and sent to the configured OpenAI transcription model only when needed.
- Transcripts, classifications, overrides, and analyzed state are stored locally in `~/Library/Application Support/Journal/journal.sqlite3`.
- Journal classification is conservative and explainable. Ambiguous recordings remain candidates for ChatGPT or the user to adjudicate.
- Filesystem access is bounded to known Voice Memos locations or `JOURNAL_VOICE_MEMOS_DIR`.
- The plugin never edits or deletes Voice Memos.

## Install on the Mac

Requirements: macOS, Python 3.11+, an OpenAI API key, and Voice Memos enabled in iCloud.

```sh
./scripts/install_macos.sh
export OPENAI_API_KEY="..."
.venv/bin/journal-doctor
```

If discovery fails, grant the terminal or service Full Disk Access and set `JOURNAL_VOICE_MEMOS_DIR` to the folder containing the synced audio files.

## Connect to ChatGPT

The server uses MCP over stdio and is intended to stay private. Create an OpenAI Secure MCP Tunnel and point its local profile at:

```sh
/absolute/path/to/journal/.venv/bin/journal-mcp
```

Run `tunnel-client doctor`, keep `tunnel-client run` active, create a developer-mode plugin using that tunnel, and name it **Journal**. No public endpoint is required.

## Tools

- `journal_status`: verify discovery and inspect index counts.
- `find_journal_entries`: retrieve recent or topic-matched entries, excluding analyzed entries by default.
- `get_journal_entry`: retrieve and, if necessary, transcribe one entry.
- `set_journal_entry_status`: correct an automatic journal classification.
- `mark_journal_entry_analyzed`: record that an entry was substantively unpacked; reversible.

## Privacy

The local SQLite index contains sensitive transcripts. It is excluded from Git and should not be placed in a synced repository. The server exposes no general-purpose file-reading tool.

