import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

# Output formats whisper can emit (and that map to a single transcript file).
VALID_FORMATS = ("txt", "srt", "vtt", "json")

# Whisper loads the whole input into one array and builds its mel-spectrogram
# before chunking internally. On Apple Silicon that array is a single Metal
# buffer; a multi-hour audiobook overflows the max buffer size and crashes. So
# we pre-split anything longer than this with ffmpeg and merge the transcripts.
# Chunks are cut at hard boundaries (no overlap), so a word straddling a seam
# can be clipped — negligible at one seam per 30 min of an audiobook.
CHUNK_SECONDS = 1800  # 30 min


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


def _duration(src: Path) -> Optional[float]:
    """Length of an audio file in seconds via ffprobe, or None if unknown."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(src)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return float(r.stdout.strip())
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def _extract_chunk(*, src: Path, start: float, dur: float, dst: Path,
                   cancel_check: Optional[Callable[[], bool]]) -> None:
    """Cut [start, start+dur) of src to a 16 kHz mono WAV — exactly what
    Whisper resamples to anyway, so each chunk stays small in memory."""
    if cancel_check and cancel_check():
        raise TranscriptionError("canceled")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-nostdin", "-ss", str(start), "-t", str(dur),
             "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
             str(dst)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except OSError as e:
        raise TranscriptionError(f"ffmpeg not available: {e}") from e
    if r.returncode != 0 or not dst.exists():
        raise TranscriptionError(r.stderr[-2000:] or "ffmpeg chunk failed")


def _shift_progress_line(line: str, offset: float) -> str:
    """Rewrite a whisper segment line "[start --> end] text" to absolute time
    by adding `offset` seconds. Per-chunk whisper restarts its clock at 0, so
    without this a progress reader sees time reset every chunk. Non-segment
    lines pass through unchanged."""
    if "-->" not in line or "[" not in line or "]" not in line:
        return line
    try:
        inside = line[line.index("[") + 1:line.index("]")]
        a, b = (s.strip() for s in inside.split("-->"))
        return (f"[{_fmt_clock(_parse_clock(a) + offset)} --> "
                f"{_fmt_clock(_parse_clock(b) + offset)}]"
                + line[line.index("]") + 1:])
    except (ValueError, IndexError):
        return line


def _parse_clock(stamp: str) -> float:
    secs = 0.0
    for p in stamp.split(":"):
        secs = secs * 60 + float(p)
    return secs


def _fmt_clock(secs: float) -> str:
    hh, rem = divmod(secs, 3600)
    mins, ss = divmod(rem, 60)
    return f"{int(hh):02d}:{int(mins):02d}:{ss:06.3f}"


def _run_whisper(*, exe: str, src: Path, dst_dir: Path, name: str, model: str,
                 fmt: str, language: Optional[str], out: Path,
                 on_progress: Optional[Callable[[str], None]],
                 cancel_check: Optional[Callable[[], bool]]) -> Path:
    """Run the Whisper CLI on one file, streaming progress; return `out`."""
    args = build_args(exe=exe, src=src, dst_dir=dst_dir, name=name,
                      model=model, fmt=fmt, language=language)
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


def transcribe(*, src: Path, model: Optional[str] = None, fmt: str = "txt",
               language: Optional[str] = "en", auto_install: bool = True,
               on_progress: Optional[Callable[[str], None]] = None,
               cancel_check: Optional[Callable[[], bool]] = None) -> Path:
    """Transcribe an audio file (e.g. a converted M4B) with a local Whisper
    model. Writes the transcript next to the source and returns its path.

    Long books are split into CHUNK_SECONDS pieces and merged, so a multi-hour
    audiobook never lands in one oversized buffer."""
    if fmt not in VALID_FORMATS:
        raise TranscriptionError(f"unsupported format: {fmt}")
    if not src.exists():
        raise TranscriptionError(f"source not found: {src}")
    if cancel_check and cancel_check():
        raise TranscriptionError("canceled")

    exe, default_model = ensure_backend(auto_install=auto_install, log=on_progress)
    model = model or default_model
    out = transcript_path(src, fmt)

    dur = _duration(src)
    if dur is None or dur <= CHUNK_SECONDS:
        return _run_whisper(exe=exe, src=src, dst_dir=src.parent, name=src.stem,
                            model=model, fmt=fmt, language=language, out=out,
                            on_progress=on_progress, cancel_check=cancel_check)

    n = math.ceil(dur / CHUNK_SECONDS)
    parts: list[tuple[str, float]] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i in range(n):
            start = i * CHUNK_SECONDS
            remaining = dur - start
            if remaining < 1.0:
                break  # negligible tail from a duration just past a boundary
            chunk = tmp / f"chunk_{i:04d}.wav"
            if on_progress:
                on_progress(f"part {i + 1}/{n}: extracting…")
            _extract_chunk(src=src, start=start, dur=min(CHUNK_SECONDS, remaining),
                           dst=chunk, cancel_check=cancel_check)
            cout = tmp / f"chunk_{i:04d}.{fmt}"
            if on_progress:
                on_progress(f"part {i + 1}/{n}: transcribing…")
            # Forward whisper progress with chunk-absolute timestamps so a
            # progress reader sees a monotonic clock across the whole book.
            chunk_progress = (
                (lambda ln, off=float(start): on_progress(_shift_progress_line(ln, off)))
                if on_progress else None)
            _run_whisper(exe=exe, src=chunk, dst_dir=tmp, name=chunk.stem,
                         model=model, fmt=fmt, language=language, out=cout,
                         on_progress=chunk_progress, cancel_check=cancel_check)
            parts.append((cout.read_text(encoding="utf-8"), float(start)))
            # Free the chunk WAV + transcript now; a long book's WAVs are GBs.
            chunk.unlink(missing_ok=True)
            cout.unlink(missing_ok=True)
        merged = _merge(parts, fmt)
    out.write_text(merged, encoding="utf-8")
    return out


_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})([.,])(\d{3})")


def _shift_timestamps(text: str, offset: float) -> str:
    """Add `offset` seconds to every HH:MM:SS,mmm / .mmm stamp in `text`."""
    def repl(m: "re.Match[str]") -> str:
        h, mm, ss, sep, ms = m.groups()
        total = int(h) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000 + offset
        hh, rem = divmod(total, 3600)
        mins, secs = divmod(rem, 60)
        whole = int(secs)
        millis = round((secs - whole) * 1000)
        return f"{int(hh):02d}:{int(mins):02d}:{whole:02d}{sep}{millis:03d}"
    return _TS.sub(repl, text)


def _merge(parts: list[tuple[str, float]], fmt: str) -> str:
    """Merge per-chunk transcripts (text, start_offset) into one document,
    re-timing the timestamped formats so they read as a single transcript."""
    if fmt == "txt":
        return "\n".join(t.strip() for t, _ in parts if t.strip()) + "\n"

    if fmt == "srt":
        blocks, n = [], 0
        for text, off in parts:
            for block in re.split(r"\n\s*\n", _shift_timestamps(text, off).strip()):
                lines = block.strip().split("\n")
                if lines and lines[0].strip().isdigit():
                    lines = lines[1:]  # drop the chunk-local cue number
                if not lines:
                    continue
                n += 1
                blocks.append(f"{n}\n" + "\n".join(lines))
        return "\n\n".join(blocks) + "\n"

    if fmt == "vtt":
        out = ["WEBVTT\n"]
        for text, off in parts:
            body = re.sub(r"^WEBVTT[^\n]*\n", "", _shift_timestamps(text, off).lstrip())
            if body.strip():
                out.append(body.strip())
        return "\n\n".join(out) + "\n"

    # json: offset every segment/word time and concatenate.
    merged: dict = {"text": "", "segments": [], "language": None}
    texts, seg_id = [], 0
    for raw, off in parts:
        data = json.loads(raw)
        merged["language"] = merged["language"] or data.get("language")
        if (data.get("text") or "").strip():
            texts.append(data["text"].strip())
        for seg in data.get("segments", []):
            seg = dict(seg)
            seg["id"] = seg_id
            seg_id += 1
            seg.pop("seek", None)  # frame offset is chunk-local; drop it
            for k in ("start", "end"):
                if k in seg:
                    seg[k] += off
            for w in seg.get("words") or []:
                for k in ("start", "end"):
                    if k in w:
                        w[k] += off
            merged["segments"].append(seg)
    merged["text"] = " ".join(texts)
    return json.dumps(merged, ensure_ascii=False)
