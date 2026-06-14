import hashlib
import shutil
from pathlib import Path

from mutagen import File as MutagenFile

from .catalog import Catalog
from .config import Config
from .models import Book

AUDIO_EXTS = {".m4b", ".m4a", ".mp3", ".aac", ".aax", ".aaxc"}


def read_meta(path: Path) -> tuple[str, str, str, int]:
    """Best-effort (title, author, narrator, runtime_min) from file tags."""
    title = author = narrator = ""
    runtime_min = 0
    try:
        mf = MutagenFile(path, easy=True)
        if mf is not None:
            tags = mf.tags or {}
            title = (tags.get("title") or [""])[0]
            author = (tags.get("artist") or tags.get("albumartist") or [""])[0]
            info = getattr(mf, "info", None)
            if info is not None and getattr(info, "length", 0):
                runtime_min = int(info.length // 60)
    except Exception:
        pass
    return title or path.stem, author or "Unknown", narrator, runtime_min


def _import_id(path: Path) -> str:
    return "import:" + hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:16]


def import_path(cfg: Config, path: Path, copy: bool = True) -> list[Book]:
    """Import a local audio file or a directory tree into the catalog.

    With copy=True (default) files are copied under the books dir; otherwise the
    catalog points at the original location.
    """
    path = Path(path)
    files = ([path] if path.is_file()
             else sorted(p for p in path.rglob("*")
                         if p.suffix.lower() in AUDIO_EXTS))
    cfg.ensure_dirs()
    catalog = Catalog(cfg.db_file)
    added: list[Book] = []
    for f in files:
        if f.suffix.lower() not in AUDIO_EXTS:
            continue
        title, author, narrator, runtime_min = read_meta(f)
        book = Book(asin=_import_id(f), title=title, author=author,
                    narrator=narrator, runtime_min=runtime_min,
                    downloaded=True, converted=True)
        if copy:
            dest = cfg.books_dir / book.safe_author / f"{book.safe_title}{f.suffix.lower()}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if f.resolve() != dest.resolve():
                shutil.copy2(f, dest)
            book.local_path = str(dest)
        else:
            book.local_path = str(f.resolve())
        catalog.add(book)
        added.append(book)
    return added
