# openaudible-py — Design

**Date:** 2026-06-14
**Status:** Approved (design); pending implementation plan

A Python reimplementation of [OpenAudible](https://openaudible.org)'s capability set:
sync your Audible library, download your purchased books, remove DRM, convert to
M4B (chapters + cover + tags), and browse/play the collection — via a CLI plus a
Textual TUI.

This is for managing **your own purchased audiobooks** with **your own Audible
credentials**. It never touches anyone else's content.

## Locked decisions

| Decision | Choice |
|---|---|
| Scope | Full clone, leaning on mature libraries (not reimplementing Audible auth/DRM from scratch) |
| Frontend | CLI + Textual TUI |
| Default output | M4B, single file, embedded chapters + cover + tags |
| Playback | Built-in, via `mpv` (libmpv) |
| Repo location | `~/Code/openaudible-py` |

## Why not just use OpenAudible / why a rewrite

OpenAudible is closed-source obfuscated Java (install4j/SWT). Its open-source
v4.8.3 tree de-DRMs **AAX only**, by recovering the 4-byte activation key offline
from the file checksum using `rcrack` + 83 MB of rainbow tables. It has **no AAXC
support** — the modern Audible download format with per-file key/IV vouchers. By
authenticating with the account and using the `audible` library, this project
handles **both AAXC and AAX**, with the rainbow-table route kept only as an
optional offline fallback.

## Approach

Build one shared core; expose it through two thin frontends (CLI + TUI). Delegate
the hard, brittle parts to maintained open-source primitives:

- **`audible`** (0.10.0) — auth, library listing, content-license/voucher,
  account activation bytes. Auth file kept **format-compatible with `audible-cli`**
  so an existing login works in either tool.
- **`ffmpeg`** (8.x) — DRM removal + remux/transcode.
- **`mutagen`** (1.47) — tag/cover/chapter writing on the output M4B.
- **`mpv`** (libmpv via `python-mpv` 1.0.8) — playback with chapter navigation.
- **`Typer`** (built on Click) — CLI; **`Textual`** (8.x) — TUI; **`rich`** — output.

### Verified facts (checked against PyPI / local / source, not memory)

- PyPI: `audible` 0.10.0, `audible-cli` 0.3.3, `python-mpv` 1.0.8, `textual` 8.2.7,
  `mutagen` 1.47.0, `rich` 15.0.0, `httpx` 0.28.1 — all present.
- Local: `ffmpeg` 8.1.1, `mpv` 0.41.0, Python 3.14.5 (dev box; target ≥3.11).
- `audible.activation_bytes.get_activation_bytes(auth)` exists (AAX key).
- AAXC voucher (key+iv) comes from the content-license request, decrypted with
  account creds — same mechanism `audible-cli`'s download command uses.
- OpenAudible 4.8.3 source: `ConvertJob.createMP3` uses
  `ffmpeg -activation_bytes <hex> -i in.aax -codec:a libmp3lame -qscale:a 6`;
  key recovery via `LookupKey` → `rcrack` + `bin/tables/*.rt` (AAX only).

## Module layout

Each unit has one purpose, a defined interface, and is testable in isolation.

```
openaudible/
  config.py     Paths + settings: base dir, default format, region, marketplace.
  models.py     Book dataclass (asin, title, authors, narrators, series, runtime,
                format[aax|aaxc], local file paths, status).
  auth.py       Wraps audible.Authenticator: login (interactive), device register,
                load/save encrypted auth.json (audible-cli compatible).
  client.py     Wraps audible.Client: list_library(), get_license(asin) -> voucher
                or download URL, get_chapters(asin), get_activation_bytes().
  catalog.py    SQLite store (library.db): sync(books), upsert, query, FTS search.
  download.py   Fetch AAX/AAXC + cover to aax/; resumable; progress callback.
  convert.py    ffmpeg pipeline -> M4B (default) | MP3 single | MP3 per-chapter.
  tag.py        mutagen: title/author/narrator/series/year/genre/desc/cover/chapters.
  keyfinder.py  Pluggable activation-bytes resolver: AccountKeyFinder (default),
                RainbowTableKeyFinder (optional, ffmpeg checksum + rcrack).
  jobs.py       Orchestrate download -> convert as cancelable jobs w/ progress;
                idempotent (skip done unless --force). Shared by CLI + TUI.
  player.py     mpv-backed: play/pause/seek/next-chapter/prev-chapter/stop.
  cli.py        Typer app: login, sync, ls, info, get, convert, play, status.
  tui/app.py    Textual: library table + detail pane + player bar + job log.
```

## Data flow

1. `login` → device registration → encrypted `auth.json`.
2. `sync` → `client.list_library()` → `catalog.sync()` upserts into `library.db`.
3. `get <asin>`:
   - `client.get_license(asin)` → AAXC voucher (key+iv) **or** AAX + account
     activation bytes.
   - `download` source + cover into `aax/`.
   - `convert` → `books/<Author>/<Title>.m4b` (stream copy; transcode only for MP3).
   - `client.get_chapters(asin)` → write chapters (ffmetadata) + tags + cover.
4. TUI calls the same `jobs` functions; no logic duplicated.

### De-DRM specifics

- **AAXC:** `ffmpeg -audible_key <k> -audible_iv <iv> -i in.aaxc -c copy
  -movflags +faststart out.m4b`
- **AAX:** `ffmpeg -activation_bytes <hex> -i in.aax -c copy
  -movflags +faststart out.m4b`
- **MP3 (opt-in):** `-codec:a libmp3lame -qscale:a 6` (single file or per-chapter
  segmented). Matches OpenAudible's quality setting.
- **Offline fallback (opt-in, not shipped):** `RainbowTableKeyFinder` runs
  `ffmpeg -i in.aax` to read `[aax] file checksum == <hash>`, then `rcrack <tablesdir>
  -h <hash>` to recover activation bytes. User supplies the tables dir.

## Storage layout

Base dir `~/Library/Application Support/openaudible-py/` (override via config / env):

```
auth.json      Encrypted authenticator (audible-cli compatible).
library.db     SQLite catalog + FTS index.
aax/           Downloaded source files (.aax/.aaxc) + raw covers.
books/         Converted output, organized <Author>/<Title>.m4b.
covers/        Extracted cover art.
config.toml    User settings.
```

## Error handling

- Auth/network failures surface actionable messages; HTTP 401 → "re-run `login`".
- `ffmpeg` non-zero exit → capture stderr tail, fail the job, leave no partial output.
- Downloads resume from partial bytes; converts are idempotent (skip if output
  exists unless `--force`).
- Jobs are cancelable; canceling cleans up temp files.

## Testing

No real Audible account needed for the suite.

- `catalog`, `models`, search, config: pure unit tests.
- `convert`/`tag`: build the ffmpeg arg vector and assert it; run the real
  stream-copy + tag path against a **tiny non-DRM `.m4a` fixture** so the ffmpeg
  and mutagen integration actually executes.
- `client`/`download`/`jobs`: `audible` client and HTTP mocked; assert license
  handling, voucher parsing, resume logic, idempotency.
- `keyfinder`: parse known `ffmpeg`/`rcrack` output strings (fixtures).
- `player`: thin; smoke-test arg construction with mpv mocked.

## Dependencies

- Python ≥ 3.11.
- PyPI: `audible`, `typer`, `textual`, `rich`, `python-mpv`, `mutagen`.
  (`httpx` comes via `audible`.)
- System: `ffmpeg`, `mpv` on PATH. Optional: `rcrack` + rainbow tables for the
  offline fallback.

## Out of scope (v1, YAGNI)

- GUI (native/web). CLI + TUI only.
- Podcast / Audible Plus catalog streaming.
- Cloud sync, multi-account.
- Shipping rainbow tables or `rcrack` binaries.

## Legal note

Distributed for personal use with your own purchased content and credentials.
DRM removal is performed locally on books you own. The README will state this.
