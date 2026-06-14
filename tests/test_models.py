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

def test_from_api_item_picks_largest_cover():
    item = {"asin": "B0", "title": "T",
            "product_images": {"252": "small.jpg", "500": "big.jpg"}}
    b = Book.from_api_item(item)
    assert b.cover_url == "big.jpg"

def test_from_api_item_no_cover():
    b = Book.from_api_item({"asin": "B0", "title": "T"})
    assert b.cover_url == ""
