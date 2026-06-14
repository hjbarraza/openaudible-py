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
    downloaded INTEGER DEFAULT 0,
    converted INTEGER DEFAULT 0
);
"""


class Catalog:
    """Local book catalog. Opens a connection per operation so it is safe to
    use from background threads (e.g. the TUI's job workers)."""

    def __init__(self, db_file: Path):
        self.db_file = Path(db_file)
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

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
            fmt=r["fmt"] or "", downloaded=bool(r["downloaded"]),
            converted=bool(r["converted"]),
        )

    def sync(self, books: Iterable[Book]) -> None:
        with self._connect() as conn:
            for b in books:
                conn.execute(
                    """INSERT INTO books
                       (asin,title,author,narrator,series,runtime_min,purchase_date,fmt)
                       VALUES (?,?,?,?,?,?,?,?)
                       ON CONFLICT(asin) DO UPDATE SET
                         title=excluded.title, author=excluded.author,
                         narrator=excluded.narrator, series=excluded.series,
                         runtime_min=excluded.runtime_min,
                         purchase_date=excluded.purchase_date""",
                    (b.asin, b.title, b.author, b.narrator, b.series,
                     b.runtime_min, b.purchase_date, b.fmt),
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
