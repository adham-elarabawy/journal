from __future__ import annotations

import json
import os

from .config import Settings
from .voice_memos import resolve_recordings_dir, scan_voice_memos


def main() -> None:
    settings = Settings.from_env()
    root = resolve_recordings_dir(settings.recordings_dir)
    memos = scan_voice_memos(root, limit=5)
    print(
        json.dumps(
            {
                "recordings_dir": str(root),
                "recent_recordings": [
                    {
                        "memo_id": memo.memo_id,
                        "title": memo.title,
                        "recorded_at": memo.recorded_at.isoformat(),
                        "duration_seconds": memo.duration_seconds,
                        "readable": os.access(memo.path, os.R_OK),
                    }
                    for memo in memos
                ],
                "openai_api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

