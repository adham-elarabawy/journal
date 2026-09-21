# Journal

Journal is a private, local-first ChatGPT plugin for reflecting on Apple Voice Memos. It reads iCloud-synced recordings from the Mac, transcribes only the memos needed for a request, identifies likely journal entries, and remembers which entries have already been discussed.

Example prompts:

- `@Journal help me understand my latest journal entry.`
- `@Journal give me your perspective on my latest entry about a decision I have been considering.`
- `@Journal find the entry from last week where I was feeling overwhelmed.`

## Design

- Voice Memos remains the source of truth.
- Audio is read locally and sent to the configured OpenAI transcription model only when needed.
- Transcripts, classifications, overrides, and analyzed state are stored locally in `~/Library/Application Support/Journal/journal.sqlite3`.
- Journal classification is conservative and explainable. Ambiguous recordings remain candidates for ChatGPT or the user to adjudicate.
- Filesystem access is bounded to known Voice Memos locations or `JOURNAL_VOICE_MEMOS_DIR`.
- The plugin never edits or deletes Voice Memos.

## Transcription

Voice Memos supplies the original audio files; Journal performs its own transcription through the OpenAI Audio API. It does not use Apple's Voice Memos transcripts. The default model is `gpt-4o-mini-transcribe`, configurable with `JOURNAL_TRANSCRIPTION_MODEL`.

Journal transcribes lazily: a request scans recent recordings and sends only the recordings needed to resolve that request. Each transcript is cached in the local SQLite index, so the same recording is not transcribed repeatedly.

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

## Everyday use

Installation, tunnel creation, and the ChatGPT plugin connection are one-time setup steps. During normal use:

1. Record in Voice Memos on an iPhone or Mac, including while offline.
2. Let iCloud sync the recording to the Mac.
3. Keep the Mac awake, online, and running `tunnel-client`.
4. Invoke `@Journal` in ChatGPT. The tunnel starts the local Journal MCP command when ChatGPT needs it.

You do not need to rerun the installer or manually import new recordings. If the tunnel process stops or the Mac is offline, Journal is temporarily unavailable; restarting `tunnel-client run` restores it. For an always-available personal setup, run the tunnel as a macOS LaunchAgent so it starts at login and restarts after failure.

## Tools

- `journal_status`: verify discovery and inspect index counts.
- `find_journal_entries`: retrieve recent or topic-matched entries, excluding analyzed entries by default.
- `get_journal_entry`: retrieve and, if necessary, transcribe one entry.
- `set_journal_entry_status`: correct an automatic journal classification.
- `mark_journal_entry_analyzed`: record that an entry was substantively unpacked; reversible.

## Privacy

The local SQLite index contains sensitive transcripts. It is excluded from Git and should not be placed in a synced repository. The server exposes no general-purpose file-reading tool.
