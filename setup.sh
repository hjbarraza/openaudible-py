#!/usr/bin/env bash
# One-shot setup for openaudible-py. Safe to re-run (idempotent).
set -euo pipefail
cd "$(dirname "$0")"

echo "==> openaudible-py setup"

have() { command -v "$1" >/dev/null 2>&1; }
OS="$(uname -s)"

# ── helpers ────────────────────────────────────────────────────────────────────
pkg_install() {
  if   have brew;    then brew install "$@"
  elif have pacman;  then sudo pacman -S --noconfirm --needed "$@"
  elif have apt-get; then sudo apt-get install -y "$@"
  elif have dnf;     then sudo dnf install -y "$@"
  else echo "!! No supported package manager (brew/pacman/apt-get/dnf)"; exit 1
  fi
}

# ── 0. Homebrew (macOS only) ───────────────────────────────────────────────────
if [ "$OS" = "Darwin" ] && ! have brew; then
  echo "==> Installing Homebrew…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$p" ] && eval "$("$p" shellenv)"
  done
  have brew || { echo "!! Homebrew install failed — see https://brew.sh"; exit 1; }
fi

# ── 1. uv — manages Python version automatically ──────────────────────────────
if ! have uv; then
  echo "==> Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
have uv || { echo "!! uv not found after install — open a new shell and re-run"; exit 1; }

# ── 2. System tools: ffmpeg + mpv ─────────────────────────────────────────────
missing=()
have ffmpeg || missing+=(ffmpeg)
have mpv    || missing+=(mpv)
if [ "${#missing[@]}" -gt 0 ]; then
  echo "==> Installing: ${missing[*]}"
  pkg_install "${missing[@]}"
fi

# ── 3. Virtualenv — uv downloads Python 3.12 automatically if absent ──────────
if [ ! -d .venv ]; then
  echo "==> Creating .venv with Python 3.12"
  uv venv .venv --python 3.12
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ── 4. Package install ─────────────────────────────────────────────────────────
echo "==> Installing package + dependencies"
uv pip install -q -e .

# ── 5. Playwright webkit + OS-level deps ──────────────────────────────────────
echo "==> Installing playwright webkit"
python -m playwright install webkit

if [ "$OS" = "Linux" ]; then
  if have pacman; then
    # Arch: playwright's pre-built webkit links against Ubuntu-specific library
    # versions (ICU 74, libwebkitgtk-6.0, libjxl 0.8) that don't exist on Arch.
    # Use system chromium instead — auth.py detects Linux and prefers it.
    echo "==> Installing chromium (used for browser login on Linux)"
    sudo pacman -S --noconfirm --needed chromium
  else
    echo "==> Installing playwright system deps"
    python -m playwright install-deps webkit
  fi
fi

# ── 6. PATH symlinks ───────────────────────────────────────────────────────────
BINDIR="$HOME/.local/bin"
mkdir -p "$BINDIR"
ln -sf "$PWD/.venv/bin/openaudible"     "$BINDIR/openaudible"
ln -sf "$PWD/.venv/bin/openaudible-tui" "$BINDIR/openaudible-tui"
echo "==> Linked openaudible, openaudible-tui → $BINDIR"
case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) echo "!! Add $BINDIR to PATH:"
     echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc  # or ~/.bashrc" ;;
esac

echo
echo "==> Setup complete."
if [ -t 1 ]; then
  echo "==> Launching openaudible-tui…"
  exec "$PWD/.venv/bin/openaudible-tui"
else
  echo "   Run: openaudible-tui"
fi
