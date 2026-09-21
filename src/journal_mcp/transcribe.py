from __future__ import annotations

from pathlib import Path


def transcribe_audio(path: Path, model: str) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the project dependencies before transcribing.") from exc

    client = OpenAI()
    with path.open("rb") as audio:
        response = client.audio.transcriptions.create(model=model, file=audio)
    text = getattr(response, "text", None)
    return str(text or "").strip()
