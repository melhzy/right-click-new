#!/usr/bin/env bash
# Right-Click New: the Windows "New" menu for Linux (GNOME Files + desktop).
#
#   ./install.sh                  templates + "New Shortcut…"
#   ./install.sh --with-deps      also apt-install python3-nautilus, zenity, pinta
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

# Desktop-file ID of Pinta (apt, Flatpak or Snap), if it is installed.
pinta_desktop_id() {
  local dirs=(
    "$DATA_HOME/applications" /usr/local/share/applications /usr/share/applications
    "$DATA_HOME/flatpak/exports/share/applications"
    /var/lib/flatpak/exports/share/applications /var/lib/snapd/desktop/applications
  )
  local id dir
  for id in com.github.PintaProject.Pinta.desktop pinta.desktop pinta_pinta.desktop; do
    for dir in "${dirs[@]}"; do
      [[ -f "$dir/$id" ]] && { echo "$id"; return 0; }
    done
  done
  return 1
}

# Make Pinta the app for .ora files (Pinta Image). The previous default is
# remembered so uninstall.sh can restore it.
set_ora_default() {
  local id="$1" current=""
  if command -v xdg-mime >/dev/null; then
    current=$(xdg-mime query default image/openraster 2>/dev/null || true)
  fi
  if [[ "$current" == "$id" ]]; then
    note "Pinta opens Pinta Image (.ora) files."
    return
  fi
  if command -v xdg-mime >/dev/null; then
    xdg-mime default "$id" image/openraster
  elif command -v gio >/dev/null; then
    gio mime image/openraster "$id" >/dev/null
  else
    note "Couldn't set Pinta as the app for .ora files (no xdg-mime or gio)."
    return
  fi
  mkdir -p "$APP_DIR"
  [[ -f "$APP_DIR/ora-default" ]] || printf '%s\n%s\n' "$id" "$current" > "$APP_DIR/ora-default"
  note "Pinta now opens Pinta Image (.ora) files${current:+ (was $current)}."
}

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

if ((with_deps)); then
  pkgs=(python3-nautilus zenity)
  pinta_desktop_id >/dev/null || pkgs+=(pinta)
  say "Installing ${pkgs[*]} (needs sudo)…"
  sudo apt-get install -y "${pkgs[@]}"
fi

say "1/3  Templates for the \"New Document\" menu"
python3 "$HERE/build_templates.py" install ${tmpl_args[@]+"${tmpl_args[@]}"}

say "2/3  Pinta for \"Pinta Image\""
if pinta_id=$(pinta_desktop_id); then
  set_ora_default "$pinta_id"
else
  note "Pinta isn't installed, so Pinta Image files have nothing to open them."
  note "Install it with:  sudo apt install pinta   (or re-run ./install.sh --with-deps)"
  note "or from Flathub:  flatpak install flathub com.github.PintaProject.Pinta"
  note "then run ./install.sh again."
fi

if ((shortcut)); then
  say "3/3  \"New Shortcut…\" menu item"
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
  say "3/3  Skipped \"New Shortcut…\" (--no-shortcut)"
fi

case "${XDG_CURRENT_DESKTOP:-}" in
  *GNOME*) ;;
  *) note "Note: you're not on GNOME. Templates also work in Nemo, Caja, Thunar and" \
          "Dolphin (via ~/Templates); New Shortcut… is GNOME Files only." ;;
esac
