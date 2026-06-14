from pathlib import Path
from typing import Callable, Optional

from .client import fetch_book
from .config import Config
from .convert import convert
from .keyfinder import account_activation_bytes
from .models import Book
from .tag import write_tags


def output_path(cfg: Config, book: Book) -> Path:
    ext = "m4b" if cfg.output_format == "m4b" else "mp3"
    return cfg.books_dir / book.safe_author / f"{book.safe_title}.{ext}"


def process_book(*, auth, cfg: Config, book: Book, force: bool = False,
                 on_progress: Optional[Callable[[str], None]] = None,
                 cancel_check: Optional[Callable[[], bool]] = None) -> Path:
    out = output_path(cfg, book)
    if out.exists() and not force:
        return out
    cfg.ensure_dirs()

    src, key, iv, _metadata = fetch_book(auth, book.asin, cfg.aax_dir,
                                         cancel_check=cancel_check)
    # AAXC ships a per-file voucher (key/iv); AAX decrypts with account bytes.
    activation_bytes = None if (key and iv) else account_activation_bytes(auth)

    # Chapters and cover are already embedded in the source; -c copy preserves
    # them, so no separate chapter/metadata injection is needed.
    out.parent.mkdir(parents=True, exist_ok=True)
    convert(src=src, dst=out, fmt=cfg.output_format,
            key=key, iv=iv, activation_bytes=activation_bytes,
            on_progress=on_progress, cancel_check=cancel_check)
    write_tags(out, book, cover_bytes=None)
    return out
