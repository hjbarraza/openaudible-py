import re
from dataclasses import dataclass, field
from typing import Any

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
    genre: str = ""
    rating: str = ""
    description: str = ""
    cover_url: str = ""
    pdf_url: str = ""
    read_status: str = ""   # "" | unread | reading | finished | dnf
    local_path: str = ""    # set for imported (non-Audible) books
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

        images = item.get("product_images") or {}
        cover_url = ""
        if images:
            largest = max(images, key=lambda k: int(k) if str(k).isdigit() else 0)
            cover_url = images[largest]

        rating = str((item.get("rating") or {}).get("overall_distribution", {})
                     .get("display_average_rating", "") or "")
        ladders = item.get("category_ladders") or []
        ladder = ladders[0].get("ladder") if ladders else None
        genre = ladder[0].get("name", "") if ladder else ""
        description = re.sub(r"<[^>]+>", "",
                             item.get("merchandising_summary") or "").strip()

        return cls(
            asin=item["asin"],
            title=item.get("title", ""),
            author=names("authors") or "Unknown",
            narrator=names("narrators"),
            series=series,
            runtime_min=int(item.get("runtime_length_min") or 0),
            purchase_date=item.get("purchase_date", "") or "",
            genre=genre,
            rating=rating,
            description=description,
            cover_url=cover_url,
            pdf_url=item.get("pdf_url", "") or "",
        )

    @property
    def safe_title(self) -> str:
        return _sanitize(self.title)

    @property
    def safe_author(self) -> str:
        return _sanitize(self.author)
