import csv
import json
from pathlib import Path

from .models import Book

FIELDS = ["asin", "title", "author", "narrator", "series", "runtime_min",
          "purchase_date", "read_status", "downloaded", "converted", "local_path"]


def _row(book: Book) -> dict:
    return {f: getattr(book, f) for f in FIELDS}


def export_catalog(books: list[Book], path: Path) -> Path:
    """Write the catalog to .json or .csv (chosen by file extension)."""
    path = Path(path)
    rows = [_row(b) for b in books]
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    return path
