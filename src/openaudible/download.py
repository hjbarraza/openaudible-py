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
