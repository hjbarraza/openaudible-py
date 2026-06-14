from pathlib import Path
from openaudible.jobs import process_book
from openaudible.models import Book
from openaudible.config import Config

EMPTY_META = {"content_metadata": {"chapter_info": {"chapters": []}}}

def test_process_book_aaxc_uses_voucher(tmp_path, monkeypatch):
    import openaudible.jobs as j
    cfg = Config(base_dir=tmp_path, books_dir=tmp_path / "books")
    cfg.ensure_dirs()
    book = Book(asin="B01", title="Title", author="Auth")

    def fake_fetch(auth, asin, aax_dir, quality="high"):
        p = Path(aax_dir) / f"{asin}.aaxc"; p.write_bytes(b"x" * 2048)
        return p, "KK", "II", EMPTY_META
    monkeypatch.setattr(j, "fetch_book", fake_fetch)
    def boom(*a, **k):
        raise AssertionError("activation bytes not needed for AAXC")
    monkeypatch.setattr(j, "account_activation_bytes", boom)
    seen = {}
    def fake_convert(**kw):
        Path(kw["dst"]).write_bytes(b"m" * 2048); seen.update(kw); return Path(kw["dst"])
    monkeypatch.setattr(j, "convert", fake_convert)
    monkeypatch.setattr(j, "write_tags", lambda *a, **k: None)

    out = process_book(auth=None, cfg=cfg, book=book)
    assert out.exists()
    assert seen["key"] == "KK" and seen["iv"] == "II"
    assert seen["activation_bytes"] is None
    assert out == cfg.books_dir / "Auth" / "Title.m4b"

def test_process_book_aax_uses_activation_bytes(tmp_path, monkeypatch):
    import openaudible.jobs as j
    cfg = Config(base_dir=tmp_path, books_dir=tmp_path / "books")
    cfg.ensure_dirs()
    book = Book(asin="B01", title="Title", author="Auth")

    def fake_fetch(auth, asin, aax_dir, quality="high"):
        p = Path(aax_dir) / f"{asin}.aax"; p.write_bytes(b"x" * 2048)
        return p, None, None, EMPTY_META  # no voucher -> AAX
    monkeypatch.setattr(j, "fetch_book", fake_fetch)
    monkeypatch.setattr(j, "account_activation_bytes", lambda auth: "deadbeef")
    seen = {}
    def fake_convert(**kw):
        Path(kw["dst"]).write_bytes(b"m" * 2048); seen.update(kw); return Path(kw["dst"])
    monkeypatch.setattr(j, "convert", fake_convert)
    monkeypatch.setattr(j, "write_tags", lambda *a, **k: None)

    out = process_book(auth=None, cfg=cfg, book=book)
    assert out.exists()
    assert seen["key"] is None and seen["iv"] is None
    assert seen["activation_bytes"] == "deadbeef"

def test_process_book_skips_when_converted(tmp_path, monkeypatch):
    import openaudible.jobs as j
    cfg = Config(base_dir=tmp_path, books_dir=tmp_path / "books")
    cfg.ensure_dirs()
    book = Book(asin="B01", title="Title", author="Auth")
    out = cfg.books_dir / "Auth" / "Title.m4b"
    out.parent.mkdir(parents=True); out.write_bytes(b"m" * 2048)
    def boom(*a, **k):
        raise AssertionError("should not be called")
    monkeypatch.setattr(j, "fetch_book", boom)
    result = process_book(auth=None, cfg=cfg, book=book)
    assert result == out
