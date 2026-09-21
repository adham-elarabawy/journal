import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from journal_mcp import transcribe


class FakeTranscriptions:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(text=result)


def install_fake_openai(monkeypatch, results):
    transcriptions = FakeTranscriptions(results)
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda: client))
    return transcriptions


def test_small_recording_uses_one_upload(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"audio")
    api = install_fake_openai(monkeypatch, ["  transcript  "])

    result = transcribe.transcribe_audio(audio, "test-model", cache_dir=tmp_path / "cache")

    assert result == "transcript"
    assert len(api.calls) == 1
    assert api.calls[0]["model"] == "test-model"


def test_large_recording_resumes_completed_chunks(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"large")
    monkeypatch.setattr(transcribe, "MAX_UPLOAD_BYTES", 4)

    def fake_split(_path, output_dir):
        parts = [output_dir / "part-0000.m4a", output_dir / "part-0001.m4a"]
        for part in parts:
            part.write_bytes(b"x")
        return parts

    monkeypatch.setattr(transcribe, "_split_audio", fake_split)
    first_api = install_fake_openai(monkeypatch, ["first", RuntimeError("temporary failure")])

    with pytest.raises(RuntimeError, match="temporary failure"):
        transcribe.transcribe_audio(audio, "test-model", cache_dir=tmp_path / "cache")
    assert len(first_api.calls) == 2

    second_api = install_fake_openai(monkeypatch, ["second"])
    result = transcribe.transcribe_audio(audio, "test-model", cache_dir=tmp_path / "cache")

    assert result == "first\n\nsecond"
    assert len(second_api.calls) == 1
    assert second_api.calls[0]["prompt"] == "first"


def test_api_error_includes_status_request_and_body(tmp_path: Path, monkeypatch) -> None:
    class APIError(Exception):
        status_code = 400
        request_id = "req_test"
        body = {"error": {"message": "bad audio"}}

    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"audio")
    install_fake_openai(monkeypatch, [APIError("Bad Request")])

    with pytest.raises(RuntimeError) as caught:
        transcribe.transcribe_audio(audio, "test-model", cache_dir=tmp_path / "cache")

    message = str(caught.value)
    assert "400" in message
    assert "req_test" in message
    assert "bad audio" in message
