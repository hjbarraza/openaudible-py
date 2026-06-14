import re
import subprocess
from pathlib import Path
from typing import Optional

_CHECKSUM = re.compile(r"\[aax\] file checksum == ([0-9a-fA-F]+)")
_RCRACK_HEX = re.compile(r"hex:([0-9a-fA-F]+)")


def parse_checksum(ffmpeg_stderr: str) -> Optional[str]:
    m = _CHECKSUM.search(ffmpeg_stderr)
    return m.group(1) if m else None


def parse_rcrack_key(rcrack_stdout: str) -> Optional[str]:
    m = _RCRACK_HEX.search(rcrack_stdout)
    return m.group(1) if m else None


def account_activation_bytes(auth) -> str:
    """Default path: fetch the account's activation bytes via the audible lib."""
    from audible.activation_bytes import get_activation_bytes
    return get_activation_bytes(auth, extract=True)


def rainbow_activation_bytes(aax: Path, tables_dir: Path,
                             rcrack: str = "rcrack") -> str:
    """Optional offline fallback (OpenAudible-style). Requires rcrack + tables."""
    r = subprocess.run(["ffmpeg", "-i", str(aax)], capture_output=True, text=True)
    checksum = parse_checksum(r.stderr)
    if not checksum:
        raise RuntimeError("could not read aax checksum from ffmpeg")
    out = subprocess.run([rcrack, str(tables_dir), "-h", checksum],
                         capture_output=True, text=True)
    key = parse_rcrack_key(out.stdout)
    if not key:
        raise RuntimeError("rcrack did not return a key")
    return key
