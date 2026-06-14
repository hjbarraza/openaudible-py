from pathlib import Path
from typing import Optional

from mutagen.mp4 import MP4, MP4Cover

from .models import Book


def build_chapter_metadata(api_metadata: dict) -> list[tuple[str, int, int]]:
    """Return [(title, start_ms, end_ms)] from a content-metadata response."""
    info = (api_metadata.get("content_metadata", {})
            .get("chapter_info", {}).get("chapters", []))
    out = []
    for ch in info:
        start = int(ch.get("start_offset_ms", 0))
        end = start + int(ch.get("length_ms", 0))
        out.append((ch.get("title", ""), start, end))
    return out


def write_tags(m4b: Path, book: Book, cover_bytes: Optional[bytes]) -> None:
    tags = MP4(m4b)
    tags["\xa9nam"] = [book.title]
    tags["\xa9ART"] = [book.author]
    tags["aART"] = [book.author]
    if book.narrator:
        tags["\xa9wrt"] = [book.narrator]
    if book.series:
        tags["\xa9alb"] = [book.series]
    tags["\xa9gen"] = ["Audiobook"]
    tags["stik"] = [2]  # iTunes media kind: audiobook
    if cover_bytes:
        tags["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
    tags.save()
