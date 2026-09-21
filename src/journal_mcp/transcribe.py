from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

# OpenAI accepts transcription uploads up to 25 MB. Files at or below the
# documented limit always use the original recording as one upload.
MAX_UPLOAD_BYTES = 25_000_000
CHUNK_SECONDS = 10 * 60


def _source_cache_key(path: Path, model: str) -> str:
    stat = path.stat()
    material = f"{path.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}\0{model}".encode()
    return hashlib.sha256(material).hexdigest()


def _split_audio(path: Path, output_dir: Path) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "This recording is too large for one transcription upload and ffmpeg is not "
            "installed. Install it with `brew install ffmpeg`, then retry."
        )

    output_pattern = output_dir / "part-%04d.m4a"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "aac",
        "-b:a",
        "48k",
        "-f",
        "segment",
        "-segment_time",
        str(CHUNK_SECONDS),
        "-segment_format",
        "mp4",
        "-reset_timestamps",
        "1",
        str(output_pattern),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown ffmpeg error").strip()
        raise RuntimeError(f"Could not split {path.name} for transcription: {detail}") from exc

    parts = sorted(output_dir.glob("part-*.m4a"))
    if not parts:
        raise RuntimeError(f"ffmpeg did not produce any audio chunks for {path.name}.")
    oversized = [part.name for part in parts if part.stat().st_size > MAX_UPLOAD_BYTES]
    if oversized:
        raise RuntimeError(
            "Generated transcription chunks still exceed the upload limit: "
            + ", ".join(oversized)
        )
    return parts


def _error_detail(exc: Exception) -> str:
    details = [str(exc).strip() or exc.__class__.__name__]
    status = getattr(exc, "status_code", None)
    request_id = getattr(exc, "request_id", None)
    body = getattr(exc, "body", None)
    if status is not None and f"status={status}" not in details[0]:
        details.append(f"status={status}")
    if request_id:
        details.append(f"request_id={request_id}")
    if body and str(body) not in details[0]:
        details.append(f"body={body}")
    return "; ".join(details)


def _transcribe_file(client: Any, path: Path, model: str, prompt: str | None = None) -> str:
    size_mb = path.stat().st_size / 1_000_000
    kwargs: dict[str, Any] = {"model": model}
    if prompt:
        kwargs["prompt"] = prompt
    try:
        with path.open("rb") as audio:
            response = client.audio.transcriptions.create(file=audio, **kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"OpenAI transcription failed for {path.name} ({size_mb:.2f} MB): "
            f"{_error_detail(exc)}"
        ) from exc
    text = getattr(response, "text", None)
    return str(text or "").strip()


def _write_text_atomically(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def transcribe_audio(path: Path, model: str, *, cache_dir: Path | None = None) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the project dependencies before transcribing.") from exc

    size = path.stat().st_size
    client = OpenAI()
    if size <= MAX_UPLOAD_BYTES:
        logger.info("Transcribing %s as one %.2f MB upload", path.name, size / 1_000_000)
        return _transcribe_file(client, path, model)

    root = cache_dir or (Path.home() / ".cache" / "journal" / "transcription-parts")
    transcript_cache = root / _source_cache_key(path, model)
    transcript_cache.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Splitting %s (%.2f MB) into resumable transcription chunks",
        path.name,
        size / 1_000_000,
    )

    with tempfile.TemporaryDirectory(prefix="journal-audio-") as temporary:
        parts = _split_audio(path, Path(temporary))
        transcripts: list[str] = []
        for index, part in enumerate(parts):
            cached = transcript_cache / f"part-{index:04d}.txt"
            if cached.exists():
                text = cached.read_text(encoding="utf-8")
                logger.info("Using cached transcript chunk %s/%s", index + 1, len(parts))
            else:
                logger.info("Transcribing chunk %s/%s", index + 1, len(parts))
                context = "\n\n".join(transcripts)[-1000:] or None
                text = _transcribe_file(client, part, model, prompt=context)
                _write_text_atomically(cached, text)
            transcripts.append(text)

    return "\n\n".join(text for text in transcripts if text).strip()
