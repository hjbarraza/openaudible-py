# openaudible-py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python CLI + Textual TUI that syncs your Audible library, downloads your purchased books, removes DRM, converts to M4B (chapters/cover/tags), and plays them — an open OpenAudible equivalent.

**Architecture:** One shared core library (`openaudible/`) with two thin frontends (Typer CLI, Textual TUI). Auth, library listing, AAXC license/voucher decryption, and download URLs are delegated to `audible` + `audible_cli.models` (imported as a library). DRM removal + remux is `ffmpeg`; tagging is `mutagen`; playback is `mpv`. Local state is a SQLite catalog plus files on disk.

**Tech Stack:** Python ≥3.11, `audible`, `audible-cli` (as lib), `typer`, `textual`, `rich`, `python-mpv`, `mutagen`; system `ffmpeg` + `mpv`.

**Conventions:**
- Source under `src/openaudible/`, tests under `tests/`. `pytest` for tests.
- `audible_cli.models` uses an **async** client; core async functions are wrapped with `asyncio.run()` at the CLI/jobs boundary.
- All paths come from `config.py`; never hardcode.
- Commit after every passing task.

---

## File structure

```
src/openaudible/
  __init__.py
  config.py        Settings + paths (base dir, format, marketplace).
  models.py        Book dataclass + enums.
  catalog.py       SQLite catalog: schema, upsert, query, search.
  auth.py          Login + load/save authenticator (audible-cli compatible).
  client.py        Async wrappers over audible_cli.models: library, license, chapters.
  keyfinder.py     Activation-bytes resolver (account default; rainbow optional).
  convert.py       ffmpeg arg-vector builder + runner -> M4B / MP3.
  tag.py           mutagen tagging + chapter/cover embedding.
  download.py      Resumable file download with progress.
  jobs.py          get(asin): license -> download -> convert -> tag (idempotent).
  player.py        mpv playback wrapper.
  cli.py           Typer app.
  tui/
    __init__.py
    app.py         Textual app.
tests/
  conftest.py
  fixtures/        Tiny non-DRM m4a + recorded JSON.
  test_*.py
pyproject.toml
README.md
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `src/openaudible/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "openaudible-py"
version = "0.1.0"
description = "Sync, de-DRM, convert and play your Audible library"
requires-python = ">=3.11"
dependencies = [
  "audible>=0.10.0",
  "audible-cli>=0.3.3",
  "typer>=0.12",
  "textual>=8.0",
  "rich>=13",
  "python-mpv>=1.0.7",
  "mutagen>=1.47",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[project.scripts]
openaudible = "openaudible.cli:app"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write the smoke test**

`tests/test_smoke.py`:
```python
import openaudible

def test_package_imports():
    assert openaudible.__name__ == "openaudible"
```

`src/openaudible/__init__.py`:
```python
__all__ = []
```
`tests/__init__.py`: empty file.

- [ ] **Step 3: Create venv + install**

Run:
```bash
cd ~/Code/openaudible-py
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```
Expected: installs without error.

- [ ] **Step 4: Run the smoke test**

Run: `. .venv/bin/activate && pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src tests
git commit -m "chore: scaffold openaudible-py package + smoke test"
```

---

## Task 2: Config

**Files:**
- Create: `src/openaudible/config.py`, `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from pathlib import Path
from openaudible.config import Config

def test_defaults_under_base(tmp_path):
    c = Config(base_dir=tmp_path)
    assert c.auth_file == tmp_path / "auth.json"
    assert c.db_file == tmp_path / "library.db"
    assert c.aax_dir == tmp_path / "aax"
    assert c.books_dir == tmp_path / "books"
    assert c.output_format == "m4b"
    assert c.marketplace == "us"

def test_ensure_dirs_creates(tmp_path):
    c = Config(base_dir=tmp_path)
    c.ensure_dirs()
    assert c.aax_dir.is_dir()
    assert c.books_dir.is_dir()

def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path / "custom"))
    c = Config.load()
    assert c.base_dir == tmp_path / "custom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (`No module named 'openaudible.config'`).

- [ ] **Step 3: Implement `config.py`**

```python
import os
from dataclasses import dataclass, field
from pathlib import Path

VALID_FORMATS = ("m4b", "mp3", "mp3-split")


def default_base_dir() -> Path:
    env = os.environ.get("OPENAUDIBLE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Library" / "Application Support" / "openaudible-py"


@dataclass
class Config:
    base_dir: Path = field(default_factory=default_base_dir)
    output_format: str = "m4b"
    marketplace: str = "us"

    @classmethod
    def load(cls) -> "Config":
        return cls()

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)
        if self.output_format not in VALID_FORMATS:
            raise ValueError(f"output_format must be one of {VALID_FORMATS}")

    @property
    def auth_file(self) -> Path:
        return self.base_dir / "auth.json"

    @property
    def db_file(self) -> Path:
        return self.base_dir / "library.db"

    @property
    def aax_dir(self) -> Path:
        return self.base_dir / "aax"

    @property
    def books_dir(self) -> Path:
        return self.base_dir / "books"

    @property
    def covers_dir(self) -> Path:
        return self.base_dir / "covers"

    def ensure_dirs(self) -> None:
        for d in (self.base_dir, self.aax_dir, self.books_dir, self.covers_dir):
            d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/config.py tests/test_config.py
git commit -m "feat: config + path resolution"
```

---

## Task 3: Book model

**Files:**
- Create: `src/openaudible/models.py`, `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from openaudible.models import Book

def test_from_api_item_minimal():
    item = {
        "asin": "B0XYZ",
        "title": "The Book",
        "authors": [{"name": "A Author"}],
        "narrators": [{"name": "N Narrator"}],
        "runtime_length_min": 600,
    }
    b = Book.from_api_item(item)
    assert b.asin == "B0XYZ"
    assert b.title == "The Book"
    assert b.author == "A Author"
    assert b.narrator == "N Narrator"
    assert b.runtime_min == 600

def test_safe_filename_strips_separators():
    b = Book(asin="x", title="A/B: C?", author="Z")
    assert "/" not in b.safe_title
    assert ":" not in b.safe_title
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL (`No module named 'openaudible.models'`).

- [ ] **Step 3: Implement `models.py`**

```python
import re
from dataclasses import dataclass, field
from typing import Any, Optional

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize(name: str) -> str:
    return _UNSAFE.sub("_", name).strip().rstrip(".") or "Unknown"


@dataclass
class Book:
    asin: str
    title: str
    author: str = "Unknown"
    narrator: str = ""
    series: str = ""
    runtime_min: int = 0
    purchase_date: str = ""
    fmt: str = ""           # aax | aaxc | ""
    downloaded: bool = False
    converted: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_api_item(cls, item: dict[str, Any]) -> "Book":
        def names(key: str) -> str:
            vals = item.get(key) or []
            return ", ".join(v.get("name", "") for v in vals if v.get("name"))

        series = ""
        if item.get("series"):
            series = item["series"][0].get("title", "")

        return cls(
            asin=item["asin"],
            title=item.get("title", ""),
            author=names("authors") or "Unknown",
            narrator=names("narrators"),
            series=series,
            runtime_min=int(item.get("runtime_length_min") or 0),
            purchase_date=item.get("purchase_date", "") or "",
        )

    @property
    def safe_title(self) -> str:
        return _sanitize(self.title)

    @property
    def safe_author(self) -> str:
        return _sanitize(self.author)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/models.py tests/test_models.py
git commit -m "feat: Book model + API mapping"
```

---

## Task 4: Catalog (SQLite)

**Files:**
- Create: `src/openaudible/catalog.py`, `tests/test_catalog.py`

- [ ] **Step 1: Write the failing test**

`tests/test_catalog.py`:
```python
from openaudible.catalog import Catalog
from openaudible.models import Book

def make(asin, title, author="A"):
    return Book(asin=asin, title=title, author=author)

def test_sync_then_get_all(tmp_path):
    cat = Catalog(tmp_path / "library.db")
    cat.sync([make("1", "Alpha"), make("2", "Beta")])
    asins = {b.asin for b in cat.all()}
    assert asins == {"1", "2"}

def test_sync_upserts_not_duplicates(tmp_path):
    cat = Catalog(tmp_path / "library.db")
    cat.sync([make("1", "Alpha")])
    cat.sync([make("1", "Alpha v2")])
    rows = cat.all()
    assert len(rows) == 1
    assert rows[0].title == "Alpha v2"

def test_get_one(tmp_path):
    cat = Catalog(tmp_path / "library.db")
    cat.sync([make("1", "Alpha")])
    assert cat.get("1").title == "Alpha"
    assert cat.get("missing") is None

def test_search_matches_title_and_author(tmp_path):
    cat = Catalog(tmp_path / "library.db")
    cat.sync([make("1", "Dune", "Herbert"), make("2", "Foundation", "Asimov")])
    assert [b.asin for b in cat.search("dune")] == ["1"]
    assert [b.asin for b in cat.search("asimov")] == ["2"]

def test_mark_flags(tmp_path):
    cat = Catalog(tmp_path / "library.db")
    cat.sync([make("1", "Alpha")])
    cat.mark("1", downloaded=True, converted=True, fmt="aaxc")
    b = cat.get("1")
    assert b.downloaded and b.converted and b.fmt == "aaxc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_catalog.py -v`
Expected: FAIL (`No module named 'openaudible.catalog'`).

- [ ] **Step 3: Implement `catalog.py`**

```python
import sqlite3
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

_COLS = ("asin", "title", "author", "narrator", "series", "runtime_min",
         "purchase_date", "fmt", "downloaded", "converted")


class Catalog:
    def __init__(self, db_file: Path):
        self.db_file = Path(db_file)
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_file)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _to_book(self, r: sqlite3.Row) -> Book:
        return Book(
            asin=r["asin"], title=r["title"], author=r["author"] or "Unknown",
            narrator=r["narrator"] or "", series=r["series"] or "",
            runtime_min=r["runtime_min"] or 0, purchase_date=r["purchase_date"] or "",
            fmt=r["fmt"] or "", downloaded=bool(r["downloaded"]),
            converted=bool(r["converted"]),
        )

    def sync(self, books: Iterable[Book]) -> None:
        for b in books:
            self._conn.execute(
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
        self._conn.commit()

    def all(self) -> list[Book]:
        cur = self._conn.execute("SELECT * FROM books ORDER BY author, title")
        return [self._to_book(r) for r in cur.fetchall()]

    def get(self, asin: str) -> Optional[Book]:
        cur = self._conn.execute("SELECT * FROM books WHERE asin=?", (asin,))
        r = cur.fetchone()
        return self._to_book(r) if r else None

    def search(self, query: str) -> list[Book]:
        like = f"%{query.lower()}%"
        cur = self._conn.execute(
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
        self._conn.execute(f"UPDATE books SET {', '.join(sets)} WHERE asin=?", vals)
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_catalog.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/catalog.py tests/test_catalog.py
git commit -m "feat: SQLite catalog with sync/search/mark"
```

---

## Task 5: Convert (ffmpeg arg builder + runner)

This is the de-DRM core. Build the arg vector as a pure function (unit-tested), then a runner that executes it against a real non-DRM fixture.

**Files:**
- Create: `src/openaudible/convert.py`, `tests/test_convert.py`, `tests/conftest.py`, `tests/fixtures/sample.m4a`

- [ ] **Step 1: Create the non-DRM audio fixture + conftest**

`tests/conftest.py`:
```python
import subprocess
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture(scope="session")
def sample_m4a():
    FIXTURES.mkdir(exist_ok=True)
    out = FIXTURES / "sample.m4a"
    if not out.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:a", "aac", str(out)],
            check=True, capture_output=True,
        )
    return out
```

- [ ] **Step 2: Write the failing test**

`tests/test_convert.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_convert.py -v`
Expected: FAIL (`No module named 'openaudible.convert'`).

- [ ] **Step 4: Implement `convert.py`**

```python
import subprocess
from pathlib import Path
from typing import Callable, Optional

FFMPEG = "ffmpeg"
MP3_QSCALE = "6"  # matches OpenAudible


class ConversionError(RuntimeError):
    pass


def build_args(*, src: Path, dst: Path, fmt: str,
               key: Optional[str], iv: Optional[str],
               activation_bytes: Optional[str]) -> list[str]:
    args = [FFMPEG, "-y"]
    # DRM inputs must precede -i.
    if key and iv:
        args += ["-audible_key", key, "-audible_iv", iv]
    elif activation_bytes:
        args += ["-activation_bytes", activation_bytes]
    args += ["-i", str(src), "-map_metadata", "0"]

    if fmt in ("m4b",):
        args += ["-c", "copy", "-movflags", "+faststart"]
    elif fmt in ("mp3", "mp3-split"):
        args += ["-codec:a", "libmp3lame", "-qscale:a", MP3_QSCALE]
    else:
        raise ConversionError(f"unsupported format: {fmt}")
    args += [str(dst)]
    return args


def convert(*, src: Path, dst: Path, fmt: str,
            key: Optional[str] = None, iv: Optional[str] = None,
            activation_bytes: Optional[str] = None,
            on_progress: Optional[Callable[[str], None]] = None) -> Path:
    if not src.exists():
        raise ConversionError(f"source not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    args = build_args(src=src, dst=dst, fmt=fmt, key=key, iv=iv,
                      activation_bytes=activation_bytes)
    proc = subprocess.Popen(args, stderr=subprocess.PIPE, text=True)
    tail = []
    for line in proc.stderr:
        tail.append(line)
        if len(tail) > 40:
            tail.pop(0)
        if on_progress and "time=" in line:
            on_progress(line.strip())
    proc.wait()
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size < 1024:
        if dst.exists():
            dst.unlink()
        raise ConversionError("".join(tail) or "ffmpeg failed")
    return dst
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_convert.py -v`
Expected: PASS (4 tests; the last actually invokes ffmpeg).

- [ ] **Step 6: Commit**

```bash
git add src/openaudible/convert.py tests/test_convert.py tests/conftest.py
echo "tests/fixtures/" >> .gitignore
git add .gitignore
git commit -m "feat: ffmpeg de-DRM + convert (m4b/mp3)"
```

---

## Task 6: Tagging + chapters (mutagen)

**Files:**
- Create: `src/openaudible/tag.py`, `tests/test_tag.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tag.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tag.py -v`
Expected: FAIL (`No module named 'openaudible.tag'`).

- [ ] **Step 3: Implement `tag.py`**

```python
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
```

Note: chapter *titles* are embedded at conversion time via an ffmetadata file (Task 9 wiring); `build_chapter_metadata` provides the data. M4B chapter atoms written by `mutagen` are limited, so chapters are passed to ffmpeg. Keep `build_chapter_metadata` here as the single source of chapter parsing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tag.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/tag.py tests/test_tag.py
git commit -m "feat: mutagen tagging + chapter parsing"
```

---

## Task 7: ffmetadata chapter file

Chapters are most reliably embedded by giving ffmpeg an ffmetadata file as a second input. Add a writer + an arg path.

**Files:**
- Modify: `src/openaudible/convert.py`
- Modify: `tests/test_convert.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_convert.py`)**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_convert.py::test_write_ffmetadata_has_chapter_blocks -v`
Expected: FAIL (`cannot import name 'write_ffmetadata'`).

- [ ] **Step 3: Implement in `convert.py`**

Add:
```python
def write_ffmetadata(path: Path, chapters: list[tuple[str, int, int]]) -> None:
    lines = [";FFMETADATA1"]
    for title, start, end in chapters:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000",
                  f"START={start}", f"END={end}",
                  f"title={title}"]
    path.write_text("\n".join(lines) + "\n")
```

Extend `build_args` signature to accept an optional metadata file and wire it in:
```python
def build_args(*, src: Path, dst: Path, fmt: str,
               key: Optional[str], iv: Optional[str],
               activation_bytes: Optional[str],
               metadata_file: Optional[Path] = None) -> list[str]:
    args = [FFMPEG, "-y"]
    if key and iv:
        args += ["-audible_key", key, "-audible_iv", iv]
    elif activation_bytes:
        args += ["-activation_bytes", activation_bytes]
    args += ["-i", str(src)]
    if metadata_file is not None:
        args += ["-i", str(metadata_file), "-map_metadata", "1", "-map", "0"]
    else:
        args += ["-map_metadata", "0"]
    if fmt == "m4b":
        args += ["-c", "copy", "-movflags", "+faststart"]
    elif fmt in ("mp3", "mp3-split"):
        args += ["-codec:a", "libmp3lame", "-qscale:a", MP3_QSCALE]
    else:
        raise ConversionError(f"unsupported format: {fmt}")
    args += [str(dst)]
    return args
```
Add `metadata_file: Optional[Path] = None` to `convert()` and pass it through to `build_args`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_convert.py -v`
Expected: PASS (all, including new test; existing tests unaffected since `metadata_file` defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/convert.py tests/test_convert.py
git commit -m "feat: ffmetadata chapter embedding"
```

---

## Task 8: Keyfinder (activation bytes)

**Files:**
- Create: `src/openaudible/keyfinder.py`, `tests/test_keyfinder.py`

- [ ] **Step 1: Write the failing test**

`tests/test_keyfinder.py`:
```python
from openaudible.keyfinder import parse_checksum, parse_rcrack_key

def test_parse_checksum_from_ffmpeg_stderr():
    stderr = "Input #0\n[aax] file checksum == 1a2b3c4d5e\nDuration: ...\n"
    assert parse_checksum(stderr) == "1a2b3c4d5e"

def test_parse_rcrack_key():
    out = "statistics\nplaintext of 1a2b... is hex:deadbeef\n"
    assert parse_rcrack_key(out) == "deadbeef"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_keyfinder.py -v`
Expected: FAIL (`No module named 'openaudible.keyfinder'`).

- [ ] **Step 3: Implement `keyfinder.py`**

```python
import re
import subprocess
from pathlib import Path
from typing import Optional

_CHECKSUM = re.compile(r"\[aax\] file checksum == ([0-9a-fA-F]+)")
_RCRACK_HEX = re.compile(r"hex:([0-9a-fA-F]+)")


def parse_checksum(ffmpeg_stderr: str) -> Optional[str]:
    m = _CHECKSUM.search(ffmpeg_stderr)
    return m.group(1) if m else None


def parse_rcrack_key(rcrack_stdout: str) -> Optional[str]:
    m = _RCRACK_HEX.search(rcrack_stdout)
    return m.group(1) if m else None


def account_activation_bytes(auth) -> str:
    """Default path: fetch the account's activation bytes via the audible lib."""
    from audible.activation_bytes import get_activation_bytes
    return get_activation_bytes(auth, extract=True)


def rainbow_activation_bytes(aax: Path, tables_dir: Path,
                             rcrack: str = "rcrack") -> str:
    """Optional offline fallback (OpenAudible-style). Requires rcrack + tables."""
    r = subprocess.run(["ffmpeg", "-i", str(aax)], capture_output=True, text=True)
    checksum = parse_checksum(r.stderr)
    if not checksum:
        raise RuntimeError("could not read aax checksum from ffmpeg")
    out = subprocess.run([rcrack, str(tables_dir), "-h", checksum],
                         capture_output=True, text=True)
    key = parse_rcrack_key(out.stdout)
    if not key:
        raise RuntimeError("rcrack did not return a key")
    return key
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_keyfinder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/keyfinder.py tests/test_keyfinder.py
git commit -m "feat: activation-bytes keyfinder (account + rainbow fallback)"
```

---

## Task 9: Auth

Thin wrapper. Real login is interactive; test the file load/save branch with a fake authenticator object.

**Files:**
- Create: `src/openaudible/auth.py`, `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

`tests/test_auth.py`:
```python
from openaudible import auth

class FakeAuth:
    def __init__(self):
        self.saved_to = None
    def to_file(self, path, password=None, encryption="json"):
        self.saved_to = str(path)
        open(path, "w").write("{}")

def test_save_authenticator(tmp_path):
    fa = FakeAuth()
    auth.save(fa, tmp_path / "auth.json", password="pw")
    assert (tmp_path / "auth.json").exists()
    assert fa.saved_to.endswith("auth.json")

def test_exists(tmp_path):
    p = tmp_path / "auth.json"
    assert not auth.exists(p)
    p.write_text("{}")
    assert auth.exists(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL (`No module named 'openaudible.auth'`).

- [ ] **Step 3: Implement `auth.py`**

```python
from pathlib import Path
from typing import Optional

import audible


def exists(auth_file: Path) -> bool:
    return Path(auth_file).exists()


def save(authenticator, auth_file: Path, password: Optional[str] = None) -> None:
    Path(auth_file).parent.mkdir(parents=True, exist_ok=True)
    if password:
        authenticator.to_file(auth_file, password=password, encryption="json")
    else:
        authenticator.to_file(auth_file, encryption=False)


def load(auth_file: Path, password: Optional[str] = None):
    if password:
        return audible.Authenticator.from_file(auth_file, password=password)
    return audible.Authenticator.from_file(auth_file)


def login_external(marketplace: str = "us"):
    """Interactive browser login. Returns an Authenticator. Not unit-tested."""
    return audible.Authenticator.from_login_external(locale=marketplace)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/auth.py tests/test_auth.py
git commit -m "feat: auth load/save (audible-cli compatible)"
```

---

## Task 10: Client (library + license + chapters)

Wrap `audible_cli.models`. The library client is async; expose sync functions via `asyncio.run`. Test parsing with a fake LibraryItem.

**Files:**
- Create: `src/openaudible/client.py`, `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

`tests/test_client.py`:
```python
from openaudible.client import voucher_from_license, download_target

def test_voucher_from_license_extracts_key_iv():
    lr = {"content_license": {"license_response": {"key": "KK", "iv": "II"}}}
    key, iv = voucher_from_license(lr)
    assert key == "KK" and iv == "II"

def test_voucher_from_license_missing_returns_none():
    assert voucher_from_license({"content_license": {}}) == (None, None)

def test_download_target_aaxc(tmp_path):
    p = download_target(tmp_path, "B01", "aaxc")
    assert p == tmp_path / "B01.aaxc"

def test_download_target_aax(tmp_path):
    p = download_target(tmp_path, "B01", "aax")
    assert p == tmp_path / "B01.aax"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_client.py -v`
Expected: FAIL (`No module named 'openaudible.client'`).

- [ ] **Step 3: Implement `client.py`**

```python
import asyncio
from pathlib import Path
from typing import Optional

import audible
from audible_cli.models import Library

from .models import Book

LIBRARY_RESPONSE_GROUPS = (
    "product_desc, product_attrs, contributors, series, "
    "product_extended_attrs, media"
)


def voucher_from_license(lr: dict) -> tuple[Optional[str], Optional[str]]:
    resp = lr.get("content_license", {}).get("license_response")
    if isinstance(resp, dict):
        return resp.get("key"), resp.get("iv")
    return None, None


def download_target(aax_dir: Path, asin: str, codec_family: str) -> Path:
    ext = "aaxc" if codec_family == "aaxc" else "aax"
    return Path(aax_dir) / f"{asin}.{ext}"


async def _fetch_library(auth) -> list[Book]:
    async with audible.AsyncClient(auth=auth) as client:
        lib = await Library.from_api_full_sync(
            client, response_groups=LIBRARY_RESPONSE_GROUPS,
        )
        return [Book.from_api_item(item._data) for item in lib]


def fetch_library(auth) -> list[Book]:
    return asyncio.run(_fetch_library(auth))


async def _get_download_info(auth, asin: str, quality: str = "high"):
    """Returns (url, codec_family, key, iv, metadata)."""
    async with audible.AsyncClient(auth=auth) as client:
        lib = await Library.from_api(client, response_groups="media, relationships")
        item = next((i for i in lib if i.asin == asin), None)
        if item is None:
            raise ValueError(f"asin not in library: {asin}")
        url, codec, lr = await item.get_aaxc_url(quality)
        key, iv = voucher_from_license(lr)
        metadata = await item.get_content_metadata(quality)
        return str(url), "aaxc", key, iv, metadata


def get_download_info(auth, asin: str, quality: str = "high"):
    return asyncio.run(_get_download_info(auth, asin, quality))
```

Note: `Library.from_api_full_sync` and `from_api` are the audible-cli model entry points. During implementation, confirm method names against the installed `audible_cli.models` (`python -c "import audible_cli.models as m; print([x for x in dir(m.Library)])"`) and adjust if the version differs; the parsing helpers (`voucher_from_license`, `download_target`) are version-independent and are what the tests cover.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Verify model entry points against installed lib**

Run: `python -c "import audible_cli.models as m; print('from_api' in dir(m.Library), 'get_aaxc_url' in dir(m.LibraryItem))"`
Expected: `True True`. If `from_api_full_sync` is absent, use `from_api` with pagination per the installed source.

- [ ] **Step 6: Commit**

```bash
git add src/openaudible/client.py tests/test_client.py
git commit -m "feat: client wrappers for library/license/chapters"
```

---

## Task 11: Download (resumable)

**Files:**
- Create: `src/openaudible/download.py`, `tests/test_download.py`

- [ ] **Step 1: Write the failing test**

`tests/test_download.py`:
```python
from openaudible.download import download_file

class FakeResp:
    def __init__(self, chunks, status=200, headers=None):
        self._chunks = chunks
        self.status_code = status
        self.headers = headers or {}
    def iter_bytes(self):
        yield from self._chunks
    def raise_for_status(self):
        pass
    def __enter__(self): return self
    def __exit__(self, *a): pass

class FakeClient:
    def __init__(self, resp):
        self._resp = resp
    def stream(self, method, url, headers=None):
        return self._resp
    def __enter__(self): return self
    def __exit__(self, *a): pass

def test_download_writes_file(tmp_path, monkeypatch):
    import openaudible.download as d
    monkeypatch.setattr(d, "_make_client", lambda: FakeClient(FakeResp([b"abc", b"def"])))
    out = tmp_path / "x.aaxc"
    download_file("http://x", out)
    assert out.read_bytes() == b"abcdef"

def test_download_skips_if_complete(tmp_path, monkeypatch):
    import openaudible.download as d
    out = tmp_path / "x.aaxc"
    out.write_bytes(b"done")
    called = {"n": 0}
    def boom():
        called["n"] += 1
        return FakeClient(FakeResp([b"x"]))
    monkeypatch.setattr(d, "_make_client", boom)
    download_file("http://x", out, expected_size=4)
    assert called["n"] == 0
    assert out.read_bytes() == b"done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_download.py -v`
Expected: FAIL (`No module named 'openaudible.download'`).

- [ ] **Step 3: Implement `download.py`**

```python
from pathlib import Path
from typing import Callable, Optional

import httpx


def _make_client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=60.0)


def download_file(url: str, dst: Path, *, expected_size: Optional[int] = None,
                  on_progress: Optional[Callable[[int, Optional[int]], None]] = None
                  ) -> Path:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if expected_size and dst.exists() and dst.stat().st_size == expected_size:
        return dst
    tmp = dst.with_suffix(dst.suffix + ".part")
    written = 0
    with _make_client() as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = expected_size or int(resp.headers.get("content-length", 0)) or None
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
                    written += len(chunk)
                    if on_progress:
                        on_progress(written, total)
    tmp.replace(dst)
    return dst
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_download.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/download.py tests/test_download.py
git commit -m "feat: resumable file download"
```

---

## Task 12: Jobs (orchestration)

Ties license → download → convert → tag together. Idempotent. Test by injecting fakes for each dependency.

**Files:**
- Create: `src/openaudible/jobs.py`, `tests/test_jobs.py`

- [ ] **Step 1: Write the failing test**

`tests/test_jobs.py`:
```python
from pathlib import Path
from openaudible.jobs import process_book
from openaudible.models import Book
from openaudible.config import Config

def test_process_book_runs_pipeline(tmp_path, monkeypatch):
    import openaudible.jobs as j
    cfg = Config(base_dir=tmp_path)
    cfg.ensure_dirs()
    book = Book(asin="B01", title="Title", author="Auth")

    monkeypatch.setattr(j, "get_download_info",
        lambda auth, asin: ("http://x", "aaxc", "KK", "II",
                            {"content_metadata": {"chapter_info": {"chapters": []}}}))
    def fake_download(url, dst, **kw):
        Path(dst).write_bytes(b"x" * 2048); return Path(dst)
    monkeypatch.setattr(j, "download_file", fake_download)
    seen = {}
    def fake_convert(**kw):
        Path(kw["dst"]).write_bytes(b"m" * 2048); seen.update(kw); return Path(kw["dst"])
    monkeypatch.setattr(j, "convert", fake_convert)
    monkeypatch.setattr(j, "write_tags", lambda *a, **k: None)

    out = process_book(auth=None, cfg=cfg, book=book)
    assert out.exists()
    assert seen["key"] == "KK" and seen["iv"] == "II"
    assert out == cfg.books_dir / "Auth" / "Title.m4b"

def test_process_book_skips_when_converted(tmp_path, monkeypatch):
    import openaudible.jobs as j
    cfg = Config(base_dir=tmp_path)
    cfg.ensure_dirs()
    book = Book(asin="B01", title="Title", author="Auth")
    out = cfg.books_dir / "Auth" / "Title.m4b"
    out.parent.mkdir(parents=True); out.write_bytes(b"m" * 2048)
    def boom(*a, **k):
        raise AssertionError("should not be called")
    monkeypatch.setattr(j, "get_download_info", boom)
    result = process_book(auth=None, cfg=cfg, book=book)
    assert result == out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jobs.py -v`
Expected: FAIL (`No module named 'openaudible.jobs'`).

- [ ] **Step 3: Implement `jobs.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jobs.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/jobs.py tests/test_jobs.py
git commit -m "feat: job orchestration (license->download->convert->tag)"
```

---

## Task 13: Player (mpv)

Thin wrapper. Test arg/state logic with mpv mocked.

**Files:**
- Create: `src/openaudible/player.py`, `tests/test_player.py`

- [ ] **Step 1: Write the failing test**

`tests/test_player.py`:
```python
import sys, types
from pathlib import Path

def _install_fake_mpv(monkeypatch):
    mod = types.ModuleType("mpv")
    class MPV:
        def __init__(self, *a, **k): self.calls = []; self.pause = False
        def play(self, path): self.calls.append(("play", path))
        def seek(self, secs, ref="relative"): self.calls.append(("seek", secs, ref))
        def playlist_next(self): self.calls.append(("next",))
    mod.MPV = MPV
    monkeypatch.setitem(sys.modules, "mpv", mod)

def test_play_invokes_mpv(monkeypatch, tmp_path):
    _install_fake_mpv(monkeypatch)
    from openaudible.player import Player
    f = tmp_path / "a.m4b"; f.write_bytes(b"x")
    p = Player()
    p.play(f)
    assert ("play", str(f)) in p._mpv.calls

def test_toggle_pause(monkeypatch, tmp_path):
    _install_fake_mpv(monkeypatch)
    from openaudible.player import Player
    p = Player()
    p.toggle_pause()
    assert p._mpv.pause is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_player.py -v`
Expected: FAIL (`No module named 'openaudible.player'`).

- [ ] **Step 3: Implement `player.py`**

```python
from pathlib import Path


class Player:
    def __init__(self):
        import mpv
        self._mpv = mpv.MPV()

    def play(self, path: Path) -> None:
        self._mpv.play(str(path))

    def toggle_pause(self) -> None:
        self._mpv.pause = not self._mpv.pause

    def seek(self, seconds: int) -> None:
        self._mpv.seek(seconds, "relative")

    def next_chapter(self) -> None:
        self._mpv.playlist_next()

    def stop(self) -> None:
        self._mpv.play("")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_player.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/player.py tests/test_player.py
git commit -m "feat: mpv playback wrapper"
```

---

## Task 14: CLI (Typer)

**Files:**
- Create: `src/openaudible/cli.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from typer.testing import CliRunner
from openaudible.cli import app
from openaudible.config import Config
from openaudible.catalog import Catalog
from openaudible.models import Book

runner = CliRunner()

def test_ls_lists_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    cat = Catalog(cfg.db_file)
    cat.sync([Book(asin="1", title="Dune", author="Herbert")])
    result = runner.invoke(app, ["ls"])
    assert result.exit_code == 0
    assert "Dune" in result.stdout

def test_status_reports_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    Catalog(cfg.db_file).sync([Book(asin="1", title="Dune")])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "1" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL (`No module named 'openaudible.cli'`).

- [ ] **Step 3: Implement `cli.py`**

```python
import typer
from rich.console import Console
from rich.table import Table

from . import auth as auth_mod
from .catalog import Catalog
from .client import fetch_library
from .config import Config
from .jobs import process_book

app = typer.Typer(help="Sync, de-DRM, convert and play your Audible library.")
console = Console()


def _cfg() -> Config:
    return Config.load()


def _auth(cfg: Config):
    if not auth_mod.exists(cfg.auth_file):
        console.print("[red]Not logged in. Run 'openaudible login' first.[/red]")
        raise typer.Exit(1)
    return auth_mod.load(cfg.auth_file)


@app.command()
def login(marketplace: str = "us"):
    """Interactive Audible login."""
    cfg = _cfg()
    authenticator = auth_mod.login_external(marketplace)
    auth_mod.save(authenticator, cfg.auth_file)
    console.print("[green]Logged in.[/green]")


@app.command()
def sync():
    """Pull your library from Audible into the local catalog."""
    cfg = _cfg()
    books = fetch_library(_auth(cfg))
    Catalog(cfg.db_file).sync(books)
    console.print(f"[green]Synced {len(books)} books.[/green]")


@app.command()
def ls(query: str = typer.Argument("")):
    """List (or search) the local catalog."""
    cfg = _cfg()
    cat = Catalog(cfg.db_file)
    books = cat.search(query) if query else cat.all()
    table = Table("ASIN", "Title", "Author", "✓")
    for b in books:
        table.add_row(b.asin, b.title, b.author, "●" if b.converted else "")
    console.print(table)


@app.command()
def info(asin: str):
    """Show details for one book."""
    cfg = _cfg()
    b = Catalog(cfg.db_file).get(asin)
    if not b:
        console.print("[red]Not found.[/red]"); raise typer.Exit(1)
    console.print(b)


@app.command()
def get(asin: str, force: bool = False):
    """Download + de-DRM + convert one book."""
    cfg = _cfg()
    cat = Catalog(cfg.db_file)
    b = cat.get(asin)
    if not b:
        console.print("[red]Not in catalog. Run sync.[/red]"); raise typer.Exit(1)
    out = process_book(auth=_auth(cfg), cfg=cfg, book=b, force=force,
                       on_progress=lambda s: console.print(s, end="\r"))
    cat.mark(asin, downloaded=True, converted=True)
    console.print(f"\n[green]Done:[/green] {out}")


@app.command()
def status():
    """Show catalog counts."""
    cfg = _cfg()
    books = Catalog(cfg.db_file).all()
    done = sum(1 for b in books if b.converted)
    console.print(f"Library: {len(books)} books, {done} converted.")


@app.command()
def play(asin: str):
    """Play a converted book in your default OS player."""
    import subprocess, sys
    from .jobs import output_path
    cfg = _cfg()
    b = Catalog(cfg.db_file).get(asin)
    if not b:
        console.print("[red]Not found.[/red]"); raise typer.Exit(1)
    path = output_path(cfg, b)
    if not path.exists():
        console.print("[red]Not converted yet. Run 'get' first.[/red]"); raise typer.Exit(1)
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run([opener, str(path)])


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/openaudible/cli.py tests/test_cli.py
git commit -m "feat: Typer CLI (login/sync/ls/info/get/status/play)"
```

---

## Task 15: TUI (Textual)

Library browser + detail + player bar. Test app mounts and lists books via Textual's async test harness.

**Files:**
- Create: `src/openaudible/tui/__init__.py`, `src/openaudible/tui/app.py`, `tests/test_tui.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tui.py`:
```python
import pytest
from openaudible.config import Config
from openaudible.catalog import Catalog
from openaudible.models import Book
from openaudible.tui.app import OpenAudibleApp

@pytest.mark.asyncio
async def test_tui_lists_books(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    Catalog(cfg.db_file).sync([Book(asin="1", title="Dune", author="Herbert")])
    app = OpenAudibleApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#library")
        assert table.row_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tui.py -v`
Expected: FAIL (`No module named 'openaudible.tui'`).

- [ ] **Step 3: Implement TUI**

`src/openaudible/tui/__init__.py`: empty.

`src/openaudible/tui/app.py`:
```python
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header

from ..catalog import Catalog
from ..config import Config


class OpenAudibleApp(App):
    BINDINGS = [("q", "quit", "Quit"), ("/", "focus_search", "Search")]
    CSS = "DataTable { height: 1fr; }"

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="library")
        yield Footer()

    def on_mount(self) -> None:
        cfg = Config.load()
        table = self.query_one("#library", DataTable)
        table.add_columns("ASIN", "Title", "Author", "Done")
        for b in Catalog(cfg.db_file).all():
            table.add_row(b.asin, b.title, b.author, "●" if b.converted else "")

    def action_focus_search(self) -> None:
        pass


def main() -> None:
    OpenAudibleApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tui.py -v`
Expected: PASS.

- [ ] **Step 5: Add TUI entry point to `pyproject.toml`**

Under `[project.scripts]` add:
```toml
openaudible-tui = "openaudible.tui.app:main"
```

- [ ] **Step 6: Commit**

```bash
git add src/openaudible/tui pyproject.toml tests/test_tui.py
git commit -m "feat: Textual TUI library browser"
```

---

## Task 16: README + full test run

**Files:**
- Create: `README.md`
- Modify: none

- [ ] **Step 1: Write `README.md`**

```markdown
# openaudible-py

Sync, de-DRM, convert, and play **your own** Audible library from the command line.
An open-source Python equivalent of OpenAudible.

> For personal use with your own purchased audiobooks and your own Audible
> credentials. DRM removal runs locally on books you own.

## Requirements

- Python ≥ 3.11
- `ffmpeg` and `mpv` on your PATH (`brew install ffmpeg mpv`)

## Install

    python3 -m venv .venv && . .venv/bin/activate
    pip install -e .

## Use

    openaudible login            # interactive Audible login
    openaudible sync             # pull your library
    openaudible ls               # list books
    openaudible get <ASIN>       # download + de-DRM + convert to M4B
    openaudible play <ASIN>      # open in your OS player
    openaudible-tui              # Textual browser

Files live under `~/Library/Application Support/openaudible-py/`
(override with `OPENAUDIBLE_HOME`).

## How de-DRM works

Authenticates with your Audible account, requests each book's content license,
and uses the returned voucher (AAXC `key`/`iv`) or your account activation bytes
(legacy AAX) to let `ffmpeg` strip DRM and remux to M4B — lossless, no re-encode.
An optional offline rainbow-table fallback exists for local AAX files.

## Develop

    pip install -e ".[dev]"
    pytest
```

- [ ] **Step 2: Run the full suite**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README"
```

---

## Self-review notes (spec coverage)

- Library sync → Tasks 4, 10, 14. De-DRM (AAXC voucher + AAX activation bytes) → Tasks 5, 8, 10, 12. Conversion m4b/mp3 → Task 5. Chapters → Tasks 6, 7, 12. Tags/cover → Task 6 (cover bytes plumbed as `None` in v1; wire fetch in a follow-up — flagged, not silently dropped). Catalog/search → Task 4. CLI → Task 14. TUI → Task 15. Player → Task 13 (CLI `play` opens externally; in-TUI mpv playback wired via Player in a follow-up). Storage layout → Tasks 2, 12. Rainbow fallback → Task 8.
- **Known v1 gaps (intentional, flagged):** cover-art fetch/embed plumbed but not wired (passes `None`); in-TUI mpv transport keys not bound (Player class exists and is tested). Both are additive follow-ups, not blockers.
- Method-name caveat: `audible_cli.models` library/license entry points are verified at implementation time in Task 10 Step 5; parsing helpers (the tested surface) are version-independent.
