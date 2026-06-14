<div align="center">

# openaudible-py

**Sync, de-DRM, convert, and play your *own* Audible library — from the terminal.**

Most Python Audible tools are command-line only. This one is a full-screen **TUI**
— cover art, live progress, search, sort, one-key downloads — with a scriptable
CLI underneath. An open-source take on OpenAudible.

![openaudible-tui](docs/tui.png)

</div>

---

## Features

<table>
<tr>
<td valign="top" width="33%">

### Library
Searchable, sortable list
(author · title · recently bought),
cover art, and a status bar.
Info panel with metadata,
rating, and description.

</td>
<td valign="top" width="33%">

### Get
Download → strip DRM → **M4B**
with chapters, cover & tags.
Companion **PDFs**, a background
**queue**, cancel, and resumable
downloads.

</td>
<td valign="top" width="33%">

### Play
**Built-in** audio player —
pause, chapter skip, speed,
seek — without leaving the
keyboard.

</td>
</tr>
<tr>
<td valign="top" width="33%">

### Manage
Read status, **edit metadata**,
auto-fill from Audible, and
**import** your own local
audiobooks.

</td>
<td valign="top" width="33%">

### Account
Browser **login** (auto-captured),
logout, and any marketplace
(`us` · `uk` · `de` · `fr` · …).

</td>
<td valign="top" width="33%">

### Terminal-native
Keyboard-first, SSH-able,
**crisp covers** on graphics
terminals, purple/mint theme,
CSV/JSON export.

</td>
</tr>
</table>

> For personal use with your own purchased audiobooks and credentials.
> DRM removal runs locally, on books you own.

## Install

```sh
git clone https://github.com/hjbarraza/openaudible-py.git
cd openaudible-py
./setup.sh        # installs deps, builds the venv, links commands onto PATH
openaudible-tui
```

`setup.sh` is idempotent. On macOS it installs Homebrew (if missing), `ffmpeg`,
`mpv`, and a compatible **Python 3.11/3.12** automatically; on Linux it lists the
packages to install. On first run it opens a browser to sign in, then press `s`
to sync. Crisp covers need a graphics terminal (Ghostty · Kitty · WezTerm · iTerm2).

<details><summary>Manual install</summary>

```sh
brew install ffmpeg mpv          # macOS; Linux: apt install ffmpeg mpv libmpv2
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
playwright install webkit        # one-time, for browser login
openaudible-tui
```
</details>

## Keys

| | | | |
|---|---|---|---|
| `Enter` get / play | `g` get | `a` get all | `c` cancel |
| `p` play | `o` folder | `m` read status | `n` notes |
| `e` edit | `F` auto-fill | `t` sort | `/` search |
| `s` sync | `l` / `L` log in / out | `r` refresh | `?` help · `q` quit |

Movement: `j` `k`, arrows, PgUp/PgDn, Home/End, `Ctrl+U` / `Ctrl+D`.
Player: `space` pause · `x` stop · `[` `]` chapter · `-` `=` speed · `f` `b` ±30s.

## CLI

```sh
openaudible login                       # browser login (auto-captures)
openaudible sync                        # pull your library
openaudible ls [query]                  # list / search
openaudible get <ASIN>                  # download + de-DRM + convert (+ PDF)
openaudible play <ASIN>                 # open in your OS player
openaudible read <ASIN> finished        # set read status
openaudible edit <ASIN> --title "..."   # edit metadata
openaudible autofill <ASIN>             # re-fetch metadata from Audible
openaudible import <path>               # import local audiobooks
openaudible export library.json         # export catalog (.json / .csv)
openaudible logout                      # deregister + clear credentials
```

`OPENAUDIBLE_NO_PDF=1` skips companion PDFs · `OPENAUDIBLE_DELETE_AAX=1` deletes
the encrypted source after converting.

## Files

| What | Where |
|---|---|
| Converted books | `~/Documents/audiobooks/<Author>/<Title>.m4b`  (`OPENAUDIBLE_BOOKS`) |
| App state (login, catalog, sources) | `~/Library/Application Support/openaudible-py/`  (`OPENAUDIBLE_HOME`) |

## How de-DRM works

Authenticates with your Audible account, requests each book's content license,
and uses the returned voucher (AAXC `key`/`iv`) or your account activation bytes
(legacy AAX) so `ffmpeg` can strip DRM and remux to M4B — lossless, no re-encode.
Chapters and cover art are preserved.

## Develop

```sh
pip install -e ".[dev]"
pytest
```
