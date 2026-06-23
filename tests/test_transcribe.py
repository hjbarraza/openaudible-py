from pathlib import Path

import pytest

import json

from openaudible import transcribe as tx
from openaudible.transcribe import (
    TranscriptionError, backends, build_args, transcript_path, transcribe,
    _merge, _shift_timestamps,
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


def test_shift_timestamps_offsets_both_separators():
    assert _shift_timestamps("00:00:01,500", 60) == "00:01:01,500"   # srt comma
    assert _shift_timestamps("00:00:02.000", 3600) == "01:00:02.000"  # vtt dot


def test_merge_txt_joins_chunks():
    assert _merge([("one.\n", 0.0), ("two.\n", 1800.0)], "txt") == "one.\ntwo.\n"


def test_merge_srt_renumbers_and_offsets():
    c0 = "1\n00:00:00,000 --> 00:00:02,000\nhello\n"
    c1 = "1\n00:00:01,000 --> 00:00:03,000\nworld\n"
    out = _merge([(c0, 0.0), (c1, 1800.0)], "srt")
    # cues renumbered 1,2 and second chunk shifted by 30 min
    assert "1\n00:00:00,000 --> 00:00:02,000\nhello" in out
    assert "2\n00:30:01,000 --> 00:30:03,000\nworld" in out


def test_merge_vtt_single_header_and_offset():
    c0 = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello\n"
    c1 = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nworld\n"
    out = _merge([(c0, 0.0), (c1, 1800.0)], "vtt")
    assert out.count("WEBVTT") == 1
    assert "00:30:01.000 --> 00:30:03.000\nworld" in out


def test_merge_json_offsets_segments_and_concatenates_text():
    c0 = json.dumps({"text": "hello", "language": "en",
                     "segments": [{"id": 0, "start": 0.0, "end": 2.0,
                                   "words": [{"start": 0.0, "end": 1.0}]}]})
    c1 = json.dumps({"text": "world", "language": "en",
                     "segments": [{"id": 0, "seek": 0, "start": 1.0, "end": 3.0}]})
    out = json.loads(_merge([(c0, 0.0), (c1, 1800.0)], "json"))
    assert out["text"] == "hello world"
    assert out["language"] == "en"
    assert [s["id"] for s in out["segments"]] == [0, 1]
    assert out["segments"][1]["start"] == 1801.0
    assert out["segments"][0]["words"][0]["end"] == 1.0
    assert "seek" not in out["segments"][1]  # chunk-local frame offset dropped
