import shutil
from pathlib import Path
from typing import Callable, Optional

from .client import download_pdf, fetch_book
from .config import Config
from .convert import ConversionError, convert
from .keyfinder import account_activation_bytes
from .models import Book
from .tag import write_tags

# Refuse to start a download when free space is below this (source + m4b + slack).
MIN_FREE_BYTES = 1_500_000_000  # ~1.5 GB


def output_path(cfg: Config, book: Book) -> Path:
    ext = "m4b" if cfg.output_format == "m4b" else "mp3"
    return cfg.books_dir / book.safe_author / f"{book.safe_title}.{ext}"


def book_file(cfg: Config, book: Book) -> Path:
    """The playable file: an imported book's real path, else the computed one."""
    return Path(book.local_path) if book.local_path else output_path(cfg, book)


def is_converted(cfg: Config, book: Book) -> bool:
    """Converted *and* the file still exists on disk (catches deletions)."""
    return book.converted and book_file(cfg, book).exists()


def _check_disk_space(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < MIN_FREE_BYTES:
        raise ConversionError(
            f"low disk space: {free // 1_000_000} MB free, "
            f"need ~{MIN_FREE_BYTES // 1_000_000} MB")


def process_book(*, auth, cfg: Config, book: Book, force: bool = False,
                 on_progress: Optional[Callable[[str], None]] = None,
                 on_download: Optional[Callable[[int, Optional[int]], None]] = None,
                 cancel_check: Optional[Callable[[], bool]] = None) -> Path:
    out = output_path(cfg, book)
    if out.exists() and not force:
        return out
    cfg.ensure_dirs()
    _check_disk_space(cfg.aax_dir)

    src, key, iv, _metadata = fetch_book(auth, book.asin, cfg.aax_dir,
                                         cancel_check=cancel_check,
                                         on_download=on_download)
    # AAXC ships a per-file voucher (key/iv); AAX decrypts with account bytes.
    activation_bytes = None if (key and iv) else account_activation_bytes(auth)

    # Chapters and cover are already embedded in the source; -c copy preserves
    # them, so no separate chapter/metadata injection is needed.
    out.parent.mkdir(parents=True, exist_ok=True)
    convert(src=src, dst=out, fmt=cfg.output_format,
            key=key, iv=iv, activation_bytes=activation_bytes,
            on_progress=on_progress, cancel_check=cancel_check)
    write_tags(out, book, cover_bytes=None)

    # Companion PDF, if the book has one (non-fatal on failure).
    if cfg.download_pdfs and book.pdf_url:
        try:
            download_pdf(auth, book.asin, out.with_suffix(".pdf"))
        except Exception:
            pass

    if cfg.delete_source and src.exists():
        src.unlink()
    return out
