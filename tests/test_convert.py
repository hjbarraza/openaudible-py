from pathlib import Path
from openaudible.convert import build_args, convert

def test_build_args_aaxc_uses_key_iv():
    args = build_args(
        src=Path("in.aaxc"), dst=Path("out.m4b"), fmt="m4b",
        key="KK", iv="II", activation_bytes=None,
    )
    assert "-audible_key" in args and "KK" in args
    assert "-audible_iv" in args and "II" in args
    assert "-c" in args and "copy" in args
    assert args[-1] == "out.m4b"

def test_build_args_aax_uses_activation_bytes():
    args = build_args(
        src=Path("in.aax"), dst=Path("out.m4b"), fmt="m4b",
        key=None, iv=None, activation_bytes="deadbeef",
    )
    assert "-activation_bytes" in args and "deadbeef" in args

def test_build_args_mp3_transcodes():
    args = build_args(
        src=Path("in.aax"), dst=Path("out.mp3"), fmt="mp3",
        key=None, iv=None, activation_bytes="deadbeef",
    )
    assert "libmp3lame" in args
    assert "-qscale:a" in args

def test_convert_runs_on_plain_audio(sample_m4a, tmp_path):
    # No DRM args -> stream copy a real file end to end.
    dst = tmp_path / "out.m4b"
    result = convert(src=sample_m4a, dst=dst, fmt="m4b",
                     key=None, iv=None, activation_bytes=None)
    assert result.exists()
    assert result.stat().st_size > 1024

from openaudible.convert import write_ffmetadata

def test_write_ffmetadata_has_chapter_blocks(tmp_path):
    p = tmp_path / "meta.txt"
    write_ffmetadata(p, [("Intro", 0, 1000), ("Body", 1000, 5000)])
    text = p.read_text()
    assert ";FFMETADATA1" in text
    assert "[CHAPTER]" in text
    assert "TIMEBASE=1/1000" in text
    assert "title=Intro" in text
    assert "START=1000" in text and "END=5000" in text
