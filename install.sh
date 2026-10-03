#!/usr/bin/env bash
# Right-Click New: the Windows "New" menu for Linux (GNOME Files + desktop).
#
#   ./install.sh                  templates + "New Shortcut…"
#   ./install.sh --with-deps      also apt-install python3-nautilus and zenity
#   ./install.sh --restart-files  restart Files afterwards (closes its windows)
#   ./install.sh --no-shortcut    templates only
#
# Any other option goes to build_templates.py, e.g.
#   ./install.sh --no-extras --paper a4 --group-extras
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/right-click-new"
EXT_DIR="$DATA_HOME/nautilus-python/extensions"

with_deps=0
restart=0
shortcut=1
tmpl_args=()
while (($#)); do
  case "$1" in
    --with-deps)     with_deps=1 ;;
    --restart-files) restart=1 ;;
    --no-shortcut)   shortcut=0 ;;
    -h|--help)       sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)               tmpl_args+=("$1") ;;
  esac
  shift
done

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }

pkg_installed() {
  dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"
}

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

if ((with_deps)); then
  say "Installing python3-nautilus and zenity (needs sudo)…"
  sudo apt-get install -y python3-nautilus zenity
fi

say "1/2  Templates for the \"New Document\" menu"
python3 "$HERE/build_templates.py" install ${tmpl_args[@]+"${tmpl_args[@]}"}

if ((shortcut)); then
  say "2/2  \"New Shortcut…\" menu item"
  install -Dm755 "$HERE/bin/new-shortcut" "$APP_DIR/new-shortcut"
  install -Dm644 "$HERE/nautilus/right_click_new.py" "$EXT_DIR/right_click_new.py"
  note "Installed the extension to $EXT_DIR"

  missing=()
  if command -v dpkg-query >/dev/null; then
    pkg_installed python3-nautilus || missing+=(python3-nautilus)
  fi
  command -v zenity >/dev/null || missing+=(zenity)
  if ((${#missing[@]})); then
    note "It needs: ${missing[*]}. Install with:"
    note "  sudo apt install ${missing[*]}"
    note "(or re-run ./install.sh --with-deps)"
  fi

  # Files' embedded Python follows PATH. Inside an activated conda env or
  # venv it picks up that Python, which has no system 'gi' module, so the
  # extension can't load in a Files window started from this shell.
  if ((restart)); then
    env PATH=/usr/local/bin:/usr/bin:/bin nautilus -q >/dev/null 2>&1 || true
    note "Files closed. Open it again from the dock or Activities."
  else
    note "Run 'nautilus -q' (closes open Files windows), then open Files from the dock."
  fi
  if [[ -n "${CONDA_PREFIX:-}${VIRTUAL_ENV:-}" ]]; then
    note "A Python environment (conda/venv) is active in this terminal. Start Files"
    note "from the dock, not from here: Files started from an activated shell can't"
    note "load Python extensions (you'd see \"No module named 'gi'\")."
  fi
else
  say "2/2  Skipped \"New Shortcut…\" (--no-shortcut)"
fi

case "${XDG_CURRENT_DESKTOP:-}" in
  *GNOME*) ;;
  *) note "Note: you're not on GNOME. Templates also work in Nemo, Caja, Thunar and" \
          "Dolphin (via ~/Templates); New Shortcut… is GNOME Files only." ;;
esac
