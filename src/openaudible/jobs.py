import tempfile
from pathlib import Path
from typing import Callable, Optional

from .client import get_download_info, download_target
from .config import Config
from .convert import convert, write_ffmetadata
from .download import download_file
from .models import Book
from .tag import build_chapter_metadata, write_tags


def output_path(cfg: Config, book: Book) -> Path:
    ext = "m4b" if cfg.output_format == "m4b" else "mp3"
    return cfg.books_dir / book.safe_author / f"{book.safe_title}.{ext}"


def process_book(*, auth, cfg: Config, book: Book, force: bool = False,
                 on_progress: Optional[Callable[[str], None]] = None) -> Path:
    out = output_path(cfg, book)
    if out.exists() and not force:
        return out
    cfg.ensure_dirs()

    url, codec_family, key, iv, metadata = get_download_info(auth, book.asin)
    src = download_target(cfg.aax_dir, book.asin, codec_family)
    download_file(url, src)

    chapters = build_chapter_metadata(metadata)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta_file = None
    if chapters and cfg.output_format == "m4b":
        meta_file = Path(tempfile.gettempdir()) / f"{book.asin}_chapters.txt"
        write_ffmetadata(meta_file, chapters)

    convert(src=src, dst=out, fmt=cfg.output_format,
            key=key, iv=iv, activation_bytes=None,
            metadata_file=meta_file, on_progress=on_progress)
    write_tags(out, book, cover_bytes=None)
    return out
