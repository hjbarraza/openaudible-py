import json
from pathlib import Path

from openaudible.config import Config
from openaudible.catalog import Catalog
from openaudible.models import Book


# ---- config flags (#6) ----
def test_config_pdf_and_delete_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    monkeypatch.delenv("OPENAUDIBLE_NO_PDF", raising=False)
    monkeypatch.delenv("OPENAUDIBLE_DELETE_AAX", raising=False)
    c = Config.load()
    assert c.download_pdfs is True and c.delete_source is False
    monkeypatch.setenv("OPENAUDIBLE_NO_PDF", "1")
    monkeypatch.setenv("OPENAUDIBLE_DELETE_AAX", "yes")
    c = Config.load()
    assert c.download_pdfs is False and c.delete_source is True


# ---- catalog read status (#3) + local book add (#4) ----
def test_read_status_round_trip(tmp_path):
    cat = Catalog(tmp_path / "l.db")
    cat.sync([Book(asin="1", title="A")])
    cat.set_read_status("1", "finished")
    assert cat.get("1").read_status == "finished"
    # sync again must not wipe read status
    cat.sync([Book(asin="1", title="A")])
    assert cat.get("1").read_status == "finished"


def test_add_local_book(tmp_path):
    cat = Catalog(tmp_path / "l.db")
    cat.add(Book(asin="import:x", title="Local", author="Me",
                 local_path="/tmp/x.m4b", converted=True, downloaded=True))
    b = cat.get("import:x")
    assert b.local_path == "/tmp/x.m4b" and b.converted and b.downloaded


# ---- exporter (#5) ----
def test_export_csv_and_json(tmp_path):
    from openaudible.exporter import export_catalog
    books = [Book(asin="1", title="Dune", author="Herbert", read_status="finished")]
    csvp = export_catalog(books, tmp_path / "x.csv")
    assert "Dune" in csvp.read_text() and "finished" in csvp.read_text()
    jsonp = export_catalog(books, tmp_path / "x.json")
    data = json.loads(jsonp.read_text())
    assert data[0]["title"] == "Dune" and data[0]["read_status"] == "finished"


# ---- importer (#4) ----
def test_import_file_copies_and_adds(tmp_path, sample_m4a, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAUDIBLE_BOOKS", str(tmp_path / "books"))
    from openaudible.importer import import_path
    cfg = Config.load()
    added = import_path(cfg, sample_m4a, copy=True)
    assert len(added) == 1
    b = added[0]
    assert b.converted and b.downloaded
    assert b.local_path and Path(b.local_path).exists()
    assert Path(b.local_path).parent == cfg.books_dir / b.safe_author
    assert Catalog(cfg.db_file).get(b.asin) is not None


# ---- jobs: book_file (#4), pdf (#1), delete source (#6) ----
def test_book_file_prefers_local_path(tmp_path):
    from openaudible.jobs import book_file
    cfg = Config(base_dir=tmp_path, books_dir=tmp_path / "b")
    assert str(book_file(cfg, Book(asin="1", title="T",
               local_path="/x/y.mp3"))) == "/x/y.mp3"


def test_process_book_pdf_and_delete_source(tmp_path, monkeypatch):
    import openaudible.jobs as j
    cfg = Config(base_dir=tmp_path, books_dir=tmp_path / "b")
    cfg.ensure_dirs()
    cfg.delete_source = True
    book = Book(asin="B1", title="T", author="A", pdf_url="http://x/p.pdf")
    holder = {}

    def fake_fetch(auth, asin, aax_dir, quality="high", cancel_check=None,
                   on_download=None):
        p = Path(aax_dir) / f"{asin}.aaxc"; p.write_bytes(b"x" * 2048)
        holder["src"] = p
        return p, "K", "I", {}

    def fake_convert(**kw):
        Path(kw["dst"]).write_bytes(b"m" * 2048); return Path(kw["dst"])

    pdfs = []
    monkeypatch.setattr(j, "fetch_book", fake_fetch)
    monkeypatch.setattr(j, "convert", fake_convert)
    monkeypatch.setattr(j, "write_tags", lambda *a, **k: None)
    monkeypatch.setattr(j, "download_pdf",
                        lambda auth, url, dst: pdfs.append((url, str(dst))))
    monkeypatch.setattr(j, "_check_disk_space", lambda p: None)

    out = j.process_book(auth=None, cfg=cfg, book=book)
    assert out.exists()
    assert pdfs and pdfs[0][0] == "B1"  # download_pdf is called with the ASIN
    assert pdfs[0][1].endswith(".pdf")
    assert not holder["src"].exists()  # source deleted after convert


# ---- metadata edit + auto-fill (#8) ----
def test_update_fields_whitelist(tmp_path):
    cat = Catalog(tmp_path / "l.db")
    cat.sync([Book(asin="1", title="Old", author="X")])
    cat.update_fields("1", title="New", author="Y", converted=True)  # converted ignored
    b = cat.get("1")
    assert b.title == "New" and b.author == "Y" and b.converted is False


# ---- deleted-file reconcile (re-download) ----
def test_is_converted_requires_file(tmp_path):
    from openaudible.jobs import is_converted, output_path
    cfg = Config(base_dir=tmp_path, books_dir=tmp_path / "b")
    book = Book(asin="1", title="T", author="A", converted=True)
    assert is_converted(cfg, book) is False        # flag set but no file
    out = output_path(cfg, book); out.parent.mkdir(parents=True); out.write_bytes(b"x")
    assert is_converted(cfg, book) is True          # file present
