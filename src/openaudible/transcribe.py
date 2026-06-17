import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

# Output formats whisper can emit (and that map to a single transcript file).
VALID_FORMATS = ("txt", "srt", "vtt", "json")


class TranscriptionError(RuntimeError):
    pass


def _apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def backends() -> list[tuple[str, str, str]]:
    """Whisper backends, fastest-first for the host OS.

    Each entry is (executable, default model, pip package that provides it).
    MLX runs Whisper on the Apple GPU/ANE — the fastest local option on Apple
    Silicon. openai-whisper (CPU/CUDA) is the portable fallback everywhere else.
    """
    if _apple_silicon():
        return [
            ("mlx_whisper", "mlx-community/whisper-base.en-mlx", "mlx-whisper"),
            ("whisper", "base.en", "openai-whisper"),
        ]
    return [("whisper", "base.en", "openai-whisper")]


def build_args(*, exe: str, src: Path, dst_dir: Path, name: str,
               model: str, fmt: str, language: Optional[str]) -> list[str]:
    """Whisper CLI args. mlx_whisper uses hyphenated flags + an HF repo model;
    openai-whisper uses underscored flags and names outputs after the input."""
    if Path(exe).name.startswith("mlx"):
        args = [exe, str(src), "--model", model,
                "--output-dir", str(dst_dir), "--output-name", name,
                "--output-format", fmt]
    else:
        # openai-whisper writes <input_stem>.<fmt> into --output_dir.
        args = [exe, str(src), "--model", model,
                "--output_dir", str(dst_dir), "--output_format", fmt]
    if language:
        args += ["--language", language]
    return args


def _resolve(exe: str) -> Optional[str]:
    # Prefer the executable shipped in this interpreter's venv, then PATH.
    cand = Path(sys.executable).parent / exe
    if cand.exists():
        return str(cand)
    return shutil.which(exe)


def ensure_backend(*, auto_install: bool = True,
                   log: Optional[Callable[[str], None]] = None) -> tuple[str, str]:
    """Return (executable, default_model), installing the fastest backend for
    this OS into the venv if none is present."""
    available = backends()
    for exe, model, _pkg in available:
        found = _resolve(exe)
        if found:
            return found, model

    exe, model, pkg = available[0]
    if not auto_install:
        raise TranscriptionError(
            f"no local Whisper backend found; install with: pip install {pkg}")
    if log:
        log(f"installing local Whisper backend ({pkg})…")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)
    except subprocess.CalledProcessError as e:
        raise TranscriptionError(f"failed to install {pkg}: {e}") from e
    found = _resolve(exe)
    if not found:
        raise TranscriptionError(f"installed {pkg} but '{exe}' is not available")
    return found, model


def transcript_path(src: Path, fmt: str = "txt") -> Path:
    return src.with_suffix("." + fmt)


def transcribe(*, src: Path, model: Optional[str] = None, fmt: str = "txt",
               language: Optional[str] = "en", auto_install: bool = True,
               on_progress: Optional[Callable[[str], None]] = None,
               cancel_check: Optional[Callable[[], bool]] = None) -> Path:
    """Transcribe an audio file (e.g. a converted M4B) with a local Whisper
    model. Writes the transcript next to the source and returns its path."""
    if fmt not in VALID_FORMATS:
        raise TranscriptionError(f"unsupported format: {fmt}")
    if not src.exists():
        raise TranscriptionError(f"source not found: {src}")
    if cancel_check and cancel_check():
        raise TranscriptionError("canceled")

    exe, default_model = ensure_backend(auto_install=auto_install, log=on_progress)
    args = build_args(exe=exe, src=src, dst_dir=src.parent, name=src.stem,
                      model=model or default_model, fmt=fmt, language=language)
    out = transcript_path(src, fmt)

    # Unbuffered child so per-segment progress lines arrive in real time.
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env)
    tail = []
    for line in proc.stdout:
        if cancel_check and cancel_check():
            proc.terminate()
            proc.wait()
            raise TranscriptionError("canceled")
        tail.append(line)
        if len(tail) > 40:
            tail.pop(0)
        if on_progress and line.strip():
            on_progress(line.strip())
    proc.wait()
    if proc.returncode != 0 or not out.exists():
        raise TranscriptionError("".join(tail) or "whisper failed")
    return out
