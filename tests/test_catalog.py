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

def test_catalog_usable_across_threads(tmp_path):
    import threading
    cat = Catalog(tmp_path / "library.db")
    cat.sync([make("1", "Alpha")])
    errors = []
    def worker():
        try:
            cat.mark("1", converted=True)
            assert cat.get("1").converted
        except Exception as e:  # pragma: no cover - failure path
            errors.append(repr(e))
    t = threading.Thread(target=worker); t.start(); t.join()
    assert errors == []
