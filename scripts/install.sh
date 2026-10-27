#!/bin/sh
# Install Dia for this user: no root, nothing outside your home.
#
#   curl -fsSL https://github.com/Solar9/Dia/releases/latest/download/install.sh | sh
#   ./scripts/install.sh                 # from a checkout: installs that checkout
#
# DIA_VERSION=0.1.0   a release (default: the latest; "main" for the development version)
# DIA_HOME=...        where Dia lives (default: ~/.local/share/dia)
# DIA_NO_SETUP=1      skip the setup wizard
set -eu

DIA_HOME="${DIA_HOME:-$HOME/.local/share/dia}"
VENV="$DIA_HOME/venv"
BIN="$HOME/.local/bin"
REPO="Solar9/Dia"
say() { printf '\033[1;35m●\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# Python 3.11 or newer
PY=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        PY="$candidate"; break
    fi
done
[ -n "$PY" ] || fail "Dia needs Python 3.11 or newer (e.g. sudo pacman -S python / sudo apt install python3)"
"$PY" -c 'import venv' 2>/dev/null || fail "Python's venv module is missing (Debian/Ubuntu: sudo apt install python3-venv)"

# What to install: this checkout, a release wheel, or the main branch
HERE="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd || true)"
if [ -n "$HERE" ] && [ -f "$HERE/pyproject.toml" ] && grep -q '^name = "dia"' "$HERE/pyproject.toml"; then
    SOURCE="$HERE"
    say "installing Dia from $SOURCE"
else
    VERSION="${DIA_VERSION:-}"
    if [ -z "$VERSION" ]; then
        VERSION="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null |
                   sed -n 's/.*"tag_name": *"v\{0,1\}\([^"]*\)".*/\1/p' | head -n1)"
    fi
    if [ -z "$VERSION" ] || [ "$VERSION" = "main" ]; then
        command -v git >/dev/null 2>&1 || fail "git is needed to install the development version"
        SOURCE="git+https://github.com/$REPO.git@main"
        say "installing Dia (development version)"
    else
        SOURCE="https://github.com/$REPO/releases/download/v$VERSION/dia-$VERSION-py3-none-any.whl"
        say "installing Dia $VERSION"
    fi
fi

mkdir -p "$DIA_HOME" "$BIN"
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
# The UI, phone pairing and push, plain chat with Claude's API. The desktop
# window with its tray icon needs Qt WebEngine (PySide6, a large download):
# tried, then pywebview, and without either Dia uses a browser app window.
case "$SOURCE" in
    /*) SPEC="$SOURCE[ui,mobile,chat]" ;;
    *) SPEC="dia[ui,mobile,chat] @ $SOURCE" ;;
esac
"$VENV/bin/python" -m pip install --quiet --upgrade "$SPEC"
if [ "${DIA_NO_QT:-}" != 1 ] && "$VENV/bin/python" -m pip install --quiet "PySide6>=6.6" 2>/dev/null; then
    say "desktop window: Qt (with a tray icon)"
else
    "$VENV/bin/python" -m pip install --quiet "pywebview>=5" 2>/dev/null || say "no desktop window library: Dia opens in a browser app window"
fi

ln -sf "$VENV/bin/dia" "$BIN/dia"
say "$("$VENV/bin/dia" --version) installed: $BIN/dia"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) say "add $BIN to your PATH (e.g. in ~/.bashrc: export PATH=\"\$HOME/.local/bin:\$PATH\")" ;;
esac

if [ -z "${DIA_NO_SETUP:-}" ]; then
    if [ -t 0 ]; then
        "$VENV/bin/dia" setup
    elif [ -r /dev/tty ]; then
        "$VENV/bin/dia" setup </dev/tty   # piped from curl: ask on the terminal
    else
        "$VENV/bin/dia" setup --yes
    fi
fi
