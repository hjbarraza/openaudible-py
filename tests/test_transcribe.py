from pathlib import Path

import pytest

from openaudible import transcribe as tx
from openaudible.transcribe import (
    TranscriptionError, backends, build_args, transcript_path, transcribe,
)


def test_backends_apple_silicon_prefers_mlx(monkeypatch):
    monkeypatch.setattr(tx, "_apple_silicon", lambda: True)
    exes = [b[0] for b in backends()]
    assert exes[0] == "mlx_whisper"          # fastest first
    assert "whisper" in exes                 # portable fallback present


def test_backends_other_os_uses_openai_whisper(monkeypatch):
    monkeypatch.setattr(tx, "_apple_silicon", lambda: False)
    assert backends() == [("whisper", "base.en", "openai-whisper")]


def test_build_args_mlx_uses_hyphenated_flags():
    args = build_args(exe="mlx_whisper", src=Path("Title.m4b"),
                      dst_dir=Path("/books"), name="Title",
                      model="mlx-community/whisper-base.en-mlx",
                      fmt="txt", language="en")
    assert "--output-dir" in args and "--output-name" in args
    assert "--output-format" in args and "txt" in args
    assert "--language" in args and "en" in args


def test_build_args_openai_uses_underscored_flags():
    args = build_args(exe="whisper", src=Path("Title.m4b"),
                      dst_dir=Path("/books"), name="Title",
                      model="base.en", fmt="srt", language=None)
    assert "--output_dir" in args and "--output_format" in args
    assert "--output-name" not in args       # openai names by input stem
    assert "--language" not in args          # omitted when language is None


def test_transcript_path_replaces_suffix():
    assert transcript_path(Path("/b/Title.m4b"), "txt") == Path("/b/Title.txt")
    assert transcript_path(Path("/b/Title.m4b"), "srt") == Path("/b/Title.srt")


def test_transcribe_rejects_bad_format(tmp_path):
    with pytest.raises(TranscriptionError, match="unsupported format"):
        transcribe(src=tmp_path / "x.m4b", fmt="docx")


def test_transcribe_missing_source_raises(tmp_path):
    with pytest.raises(TranscriptionError, match="not found"):
        transcribe(src=tmp_path / "missing.m4b")


def test_transcribe_cancel_before_start_raises(tmp_path):
    src = tmp_path / "x.m4b"
    src.write_bytes(b"\0" * 2048)
    with pytest.raises(TranscriptionError, match="canceled"):
        transcribe(src=src, cancel_check=lambda: True)
