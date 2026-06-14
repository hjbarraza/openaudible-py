import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

from .models import Book

_SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    asin TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    narrator TEXT,
    series TEXT,
    runtime_min INTEGER,
    purchase_date TEXT,
    fmt TEXT,
    cover_url TEXT,
    pdf_url TEXT,
    read_status TEXT,
    local_path TEXT,
    downloaded INTEGER DEFAULT 0,
    converted INTEGER DEFAULT 0
);
"""

_MIGRATIONS = {"cover_url": "TEXT", "pdf_url": "TEXT", "read_status": "TEXT",
               "local_path": "TEXT"}


class Catalog:
    """Local book catalog. Opens a connection per operation so it is safe to
    use from background threads (e.g. the TUI's job workers)."""

    def __init__(self, db_file: Path):
        self.db_file = Path(db_file)
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(books)")}
            for name, sqltype in _MIGRATIONS.items():  # migrate older databases
                if name not in cols:
                    conn.execute(f"ALTER TABLE books ADD COLUMN {name} {sqltype}")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _to_book(self, r: sqlite3.Row) -> Book:
        return Book(
            asin=r["asin"], title=r["title"], author=r["author"] or "Unknown",
            narrator=r["narrator"] or "", series=r["series"] or "",
            runtime_min=r["runtime_min"] or 0, purchase_date=r["purchase_date"] or "",
            fmt=r["fmt"] or "",
            cover_url=(r["cover_url"] if "cover_url" in r.keys() else "") or "",
            pdf_url=(r["pdf_url"] if "pdf_url" in r.keys() else "") or "",
            read_status=(r["read_status"] if "read_status" in r.keys() else "") or "",
            local_path=(r["local_path"] if "local_path" in r.keys() else "") or "",
            downloaded=bool(r["downloaded"]), converted=bool(r["converted"]),
        )

    def sync(self, books: Iterable[Book]) -> None:
        with self._connect() as conn:
            for b in books:
                conn.execute(
                    """INSERT INTO books
                       (asin,title,author,narrator,series,runtime_min,
                        purchase_date,fmt,cover_url,pdf_url)
                       VALUES (?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(asin) DO UPDATE SET
                         title=excluded.title, author=excluded.author,
                         narrator=excluded.narrator, series=excluded.series,
                         runtime_min=excluded.runtime_min,
                         purchase_date=excluded.purchase_date,
                         cover_url=excluded.cover_url, pdf_url=excluded.pdf_url""",
                    (b.asin, b.title, b.author, b.narrator, b.series,
                     b.runtime_min, b.purchase_date, b.fmt, b.cover_url, b.pdf_url),
                )

    def add(self, book: Book) -> None:
        """Insert/replace a single book including local_path (used by import)."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO books
                   (asin,title,author,narrator,series,runtime_min,purchase_date,
                    fmt,cover_url,pdf_url,read_status,local_path,downloaded,converted)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (book.asin, book.title, book.author, book.narrator, book.series,
                 book.runtime_min, book.purchase_date, book.fmt, book.cover_url,
                 book.pdf_url, book.read_status, book.local_path,
                 int(book.downloaded), int(book.converted)),
            )

    def all(self) -> list[Book]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM books ORDER BY author, title")
            return [self._to_book(r) for r in cur.fetchall()]

    def get(self, asin: str) -> Optional[Book]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM books WHERE asin=?", (asin,))
            r = cur.fetchone()
            return self._to_book(r) if r else None

    def search(self, query: str) -> list[Book]:
        like = f"%{query.lower()}%"
        with self._connect() as conn:
            cur = conn.execute(
                """SELECT * FROM books
                   WHERE lower(title) LIKE ? OR lower(author) LIKE ?
                      OR lower(series) LIKE ? OR lower(narrator) LIKE ?
                   ORDER BY author, title""",
                (like, like, like, like),
            )
            return [self._to_book(r) for r in cur.fetchall()]

    def mark(self, asin: str, *, downloaded: bool = None,
             converted: bool = None, fmt: str = None) -> None:
        sets, vals = [], []
        if downloaded is not None:
            sets.append("downloaded=?"); vals.append(int(downloaded))
        if converted is not None:
            sets.append("converted=?"); vals.append(int(converted))
        if fmt is not None:
            sets.append("fmt=?"); vals.append(fmt)
        if not sets:
            return
        vals.append(asin)
        with self._connect() as conn:
            conn.execute(f"UPDATE books SET {', '.join(sets)} WHERE asin=?", vals)

    def set_read_status(self, asin: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE books SET read_status=? WHERE asin=?",
                         (status, asin))

    EDITABLE = ("title", "author", "narrator", "series")

    def update_fields(self, asin: str, **fields) -> None:
        cols = [c for c in fields if c in self.EDITABLE]
        if not cols:
            return
        sets = ", ".join(f"{c}=?" for c in cols)
        vals = [fields[c] for c in cols] + [asin]
        with self._connect() as conn:
            conn.execute(f"UPDATE books SET {sets} WHERE asin=?", vals)
