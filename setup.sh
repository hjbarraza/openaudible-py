#!/usr/bin/env bash
# One-shot setup for openaudible-py. Safe to re-run (idempotent).
set -euo pipefail
cd "$(dirname "$0")"

echo "==> openaudible-py setup"

have() { command -v "$1" >/dev/null 2>&1; }

# 1. system tools: ffmpeg (convert) + mpv/libmpv (in-app playback)
missing=()
have ffmpeg || missing+=(ffmpeg)
have mpv    || missing+=(mpv)
if [ "${#missing[@]}" -gt 0 ]; then
  if have brew; then
    echo "==> installing: ${missing[*]}"
    brew install "${missing[@]}"
  else
    echo "!! Missing: ${missing[*]}"
    echo "   Install them, then re-run. Examples:"
    echo "     Debian/Ubuntu:  sudo apt install ffmpeg mpv libmpv2"
    echo "     Fedora:         sudo dnf install ffmpeg mpv"
    exit 1
  fi
fi

# 2. virtualenv
PY="${PYTHON:-python3}"
[ -d .venv ] || { echo "==> creating .venv"; "$PY" -m venv .venv; }
# shellcheck disable=SC1091
source .venv/bin/activate

# 3. install the package
echo "==> installing package + dependencies"
pip install -q --upgrade pip
pip install -q -e .

# 4. browser for login
echo "==> installing playwright webkit (for browser login)"
python -m playwright install webkit

# 5. put the commands on PATH
BINDIR="$HOME/.local/bin"
mkdir -p "$BINDIR"
ln -sf "$PWD/.venv/bin/openaudible" "$BINDIR/openaudible"
ln -sf "$PWD/.venv/bin/openaudible-tui" "$BINDIR/openaudible-tui"
echo "==> linked openaudible, openaudible-tui -> $BINDIR"
case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) echo "!! Add $BINDIR to PATH:"
     echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc" ;;
esac

echo
echo "Done. Launch with:  openaudible-tui"
