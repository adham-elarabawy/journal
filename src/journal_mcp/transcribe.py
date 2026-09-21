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
    if not text:
        raise RuntimeError("The transcription API returned no text.")
    return str(text).strip()

