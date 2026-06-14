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
