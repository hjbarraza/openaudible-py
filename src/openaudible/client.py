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
