import subprocess
from pathlib import Path
from typing import Callable, Optional

FFMPEG = "ffmpeg"
MP3_QSCALE = "6"  # matches OpenAudible


class ConversionError(RuntimeError):
    pass


def build_args(*, src: Path, dst: Path, fmt: str,
               key: Optional[str], iv: Optional[str],
               activation_bytes: Optional[str]) -> list[str]:
    args = [FFMPEG, "-y"]
    # DRM inputs must precede -i.
    if key and iv:
        args += ["-audible_key", key, "-audible_iv", iv]
    elif activation_bytes:
        args += ["-activation_bytes", activation_bytes]
    # -c copy preserves the chapters and cover already embedded in the source.
    args += ["-i", str(src), "-map_metadata", "0"]

    if fmt == "m4b":
        args += ["-c", "copy", "-movflags", "+faststart"]
    elif fmt in ("mp3", "mp3-split"):
        args += ["-codec:a", "libmp3lame", "-qscale:a", MP3_QSCALE]
    else:
        raise ConversionError(f"unsupported format: {fmt}")
    args += [str(dst)]
    return args


def convert(*, src: Path, dst: Path, fmt: str,
            key: Optional[str] = None, iv: Optional[str] = None,
            activation_bytes: Optional[str] = None,
            on_progress: Optional[Callable[[str], None]] = None,
            cancel_check: Optional[Callable[[], bool]] = None) -> Path:
    if not src.exists():
        raise ConversionError(f"source not found: {src}")
    if cancel_check and cancel_check():
        raise ConversionError("canceled")
    dst.parent.mkdir(parents=True, exist_ok=True)
    args = build_args(src=src, dst=dst, fmt=fmt, key=key, iv=iv,
                      activation_bytes=activation_bytes)
    proc = subprocess.Popen(args, stderr=subprocess.PIPE, text=True)
    tail = []
    for line in proc.stderr:
        if cancel_check and cancel_check():
            proc.terminate()
            proc.wait()
            if dst.exists():
                dst.unlink()
            raise ConversionError("canceled")
        tail.append(line)
        if len(tail) > 40:
            tail.pop(0)
        if on_progress and "time=" in line:
            on_progress(line.strip())
    proc.wait()
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size < 1024:
        if dst.exists():
            dst.unlink()
        raise ConversionError("".join(tail) or "ffmpeg failed")
    return dst
