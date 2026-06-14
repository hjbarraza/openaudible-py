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


DOWNLOAD_RESPONSE_GROUPS = (
    "product_desc, media, product_attrs, relationships, "
    "series, customer_rights, pdf_url"
)

# CloudFront 403s downloads without the Audible app User-Agent (matches audible-cli).
DOWNLOAD_USER_AGENT = "Audible/671 CFNetwork/1240.0.4 Darwin/20.6.0"


async def _stream_to_file(session, url: str, dst: Path, cancel_check=None,
                          on_progress=None) -> None:
    # The signed CloudFront URL must be fetched through Audible's authenticated
    # session; a bare httpx client gets a 403.
    tmp = dst.with_suffix(dst.suffix + ".part")
    with open(tmp, "wb") as fh:
        async with session.stream("GET", url, follow_redirects=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0) or None
            written = 0
            async for chunk in resp.aiter_bytes():
                if cancel_check and cancel_check():
                    raise RuntimeError("canceled")
                fh.write(chunk)
                written += len(chunk)
                if on_progress:
                    on_progress(written, total)
    tmp.replace(dst)


async def _fetch_book(auth, asin: str, aax_dir: Path, quality: str = "high",
                      cancel_check=None, on_download=None):
    """Download the source file via the authed session.

    Returns (src_path, key, iv, metadata). key/iv are set for AAXC; for AAX they
    are None and the caller decrypts with the account activation bytes.
    """
    async with audible.AsyncClient(auth=auth) as client:
        client.session.headers["User-Agent"] = DOWNLOAD_USER_AGENT
        # from_api returns only one page (~50 items); paginate so books past the
        # first page are found. customer_rights is required for is_downloadable().
        lib = await Library.from_api_full_sync(
            client, response_groups=DOWNLOAD_RESPONSE_GROUPS)
        item = next((i for i in lib if i.asin == asin), None)
        if item is None:
            raise ValueError(f"asin not in library: {asin}")
        url, _codec, lr = await item.get_aaxc_url(quality)
        key, iv = voucher_from_license(lr)
        # Flat chapters avoid dropping nested sub-chapters in tree responses.
        metadata = await item.get_content_metadata(quality, chapter_type="Flat")
        ext = "aaxc" if ".aaxc" in str(url).lower() else "aax"
        dst = Path(aax_dir) / f"{asin}.{ext}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        await _stream_to_file(client.session, str(url), dst, cancel_check,
                              on_download)
        return dst, key, iv, metadata


def fetch_book(auth, asin: str, aax_dir: Path, quality: str = "high",
               cancel_check=None, on_download=None):
    return asyncio.run(
        _fetch_book(auth, asin, aax_dir, quality, cancel_check, on_download))
