#!/usr/bin/env bash
# One-shot setup for openaudible-py. Safe to re-run (idempotent).
set -euo pipefail
cd "$(dirname "$0")"

echo "==> openaudible-py setup"

have() { command -v "$1" >/dev/null 2>&1; }

# 0. Homebrew (macOS) — used to install ffmpeg/mpv
if [ "$(uname)" = "Darwin" ] && ! have brew; then
  echo "==> Homebrew not found — installing…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$p" ] && eval "$("$p" shellenv)"
  done
  have brew || { echo "!! Homebrew install did not complete; see https://brew.sh"; exit 1; }
fi

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

# 2. virtualenv — needs Python 3.11 or 3.12 (the audible lib requires <3.13)
pick_python() {
  for c in "${PYTHON:-}" python3.12 python3.11 python3; do
    [ -n "$c" ] && have "$c" || continue
    if "$c" - <<'EOF' 2>/dev/null
import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)
EOF
    then echo "$c"; return 0; fi
  done
  return 1
}
if [ ! -d .venv ]; then
  PY="$(pick_python)" || {
    echo "!! Need Python 3.11 or 3.12 (the 'audible' library requires <3.13)."
    echo "   macOS:  brew install python@3.12   then re-run."
    exit 1
  }
  echo "==> creating .venv with $("$PY" -V)"
  "$PY" -m venv .venv
fi
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
echo "==> Setup complete. Launching openaudible-tui (it will open a browser to sign in)…"
if [ -t 1 ]; then
  exec "$PWD/.venv/bin/openaudible-tui"
else
  echo "   Not a terminal; run 'openaudible-tui' yourself."
fi
