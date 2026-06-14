from pathlib import Path
import subprocess
from mutagen.mp4 import MP4
from openaudible.models import Book
from openaudible.tag import write_tags, build_chapter_metadata

def _m4b(tmp_path, sample_m4a):
    dst = tmp_path / "b.m4b"
    subprocess.run(["ffmpeg", "-y", "-i", str(sample_m4a), "-c", "copy", str(dst)],
                   check=True, capture_output=True)
    return dst

def test_write_tags_sets_fields(tmp_path, sample_m4a):
    dst = _m4b(tmp_path, sample_m4a)
    book = Book(asin="x", title="My Title", author="Jane Doe",
                narrator="Reader", series="Saga")
    write_tags(dst, book, cover_bytes=None)
    tags = MP4(dst)
    assert tags["\xa9nam"] == ["My Title"]
    assert tags["\xa9ART"] == ["Jane Doe"]

def test_build_chapter_metadata_from_api():
    md = {"content_metadata": {"chapter_info": {"chapters": [
        {"title": "Ch 1", "start_offset_ms": 0, "length_ms": 1000},
        {"title": "Ch 2", "start_offset_ms": 1000, "length_ms": 2000},
    ]}}}
    chapters = build_chapter_metadata(md)
    assert chapters[0] == ("Ch 1", 0, 1000)
    assert chapters[1] == ("Ch 2", 1000, 3000)
