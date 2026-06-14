# openaudible-py

Sync, de-DRM, convert, and play **your own** Audible library from the command line.
An open-source Python equivalent of OpenAudible.

> For personal use with your own purchased audiobooks and your own Audible
> credentials. DRM removal runs locally on books you own.

## Requirements

- Python ≥ 3.11
- `ffmpeg` and `mpv` on your PATH (`brew install ffmpeg mpv`)

## Install

    python3 -m venv .venv && . .venv/bin/activate
    pip install -e .
    playwright install webkit    # one-time, for browser login

## Use

    openaudible login            # opens a browser, signs you in automatically
    openaudible sync             # pull your library
    openaudible ls               # list books
    openaudible get <ASIN>       # download + de-DRM + convert to M4B
    openaudible play <ASIN>      # open in your OS player
    openaudible-tui              # Textual browser

Converted books go to `~/Documents/audiobooks/<Author>/<Title>.m4b`
(override with `OPENAUDIBLE_BOOKS`). App state — login, catalog, and the
encrypted source files — lives under `~/Library/Application Support/openaudible-py/`
(override with `OPENAUDIBLE_HOME`).

### Login

`openaudible login` opens a browser, you sign in to Amazon, and it captures the
result automatically — no copy/paste. Add `--marketplace uk` (or `de`, `fr`,
`ca`, `it`, `au`) for a non-US account.

No browser available? Use the manual flow:

    openaudible login --manual                 # prints a URL to open
    openaudible login --manual --url "<URL>"   # paste the post-login URL back

## How de-DRM works

Authenticates with your Audible account, requests each book's content license,
and uses the returned voucher (AAXC `key`/`iv`) or your account activation bytes
(legacy AAX) to let `ffmpeg` strip DRM and remux to M4B — lossless, no re-encode.
An optional offline rainbow-table fallback exists for local AAX files.

## Develop

    pip install -e ".[dev]"
    pytest
