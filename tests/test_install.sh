#!/usr/bin/env bash
# End-to-end install/uninstall tests in a throwaway HOME.
# Checks are eval'd strings, and '$HOME' in printf is written literally on
# purpose (that's the user-dirs.dirs syntax), so silence those lints:
# (SC2317 is what older ShellCheck releases report instead of SC2329.)
# shellcheck disable=SC2016,SC2034,SC2317,SC2329
set -uo pipefail
PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"
trap 'rm -rf "$S"' EXIT
export HOME="$S/home"
unset XDG_DATA_HOME XDG_CONFIG_HOME
mkdir -p "$HOME"
T="$HOME/Templates"
fail=0
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi; }
count() { find "$1" -maxdepth 1 -type f | wc -l; }
bt() { python3 "$PKG/build_templates.py" "$@"; }

echo "== fresh install (no user-dirs.dirs) =="
XDG_CURRENT_DESKTOP=ubuntu:GNOME "$PKG/install.sh" >/dev/null
check "Templates folder registered" "grep -q 'XDG_TEMPLATES_DIR=\"\$HOME/Templates\"' '$HOME/.config/user-dirs.dirs'"
check "13 templates added" "[[ \$(count '$T') == 13 ]]"
check "extension installed" "[[ -f '$HOME/.local/share/nautilus-python/extensions/right_click_new.py' ]]"
check "helper executable" "[[ -x '$HOME/.local/share/right-click-new/new-shortcut' ]]"
check "manifest written" "[[ -f '$HOME/.local/share/right-click-new/manifest.json' ]]"

echo "== re-run is a no-op =="
out=$(bt install)
check "all unchanged" "grep -q 'Done: 13 unchanged' <<<\"\$out\""

echo "== edited template is protected =="
echo "my notes" > "$T/Text Document.txt"
out=$(bt install)
check "edited file skipped" "grep -q 'skipped    Text Document.txt' <<<\"\$out\""
check "edit preserved" "[[ \$(cat '$T/Text Document.txt') == 'my notes' ]]"
bt install --force >/dev/null
check "--force replaces" "[[ ! -s '$T/Text Document.txt' ]]"
check "--force backs up first" "grep -rq 'my notes' '$HOME/.local/share/right-click-new/backup'"

echo "== option changes =="
bt install --no-extras >/dev/null
check "--no-extras prunes to 6" "[[ \$(count '$T') == 6 ]]"
bt install --group-extras >/dev/null
check "--group-extras: 6 + 7 in folder" "[[ \$(count '$T') == 6 && \$(count '$T/Code and Data') == 7 ]]"
bt install >/dev/null
check "ungrouping removes folder" "[[ ! -e '$T/Code and Data' && \$(count '$T') == 13 ]]"

echo "== Templates folder handling =="
printf 'XDG_DESKTOP_DIR="$HOME/Desktop"\nXDG_TEMPLATES_DIR="$HOME/"\n' > "$HOME/.config/user-dirs.dirs"
out=$(bt install)
check "disabled folder re-enabled" "grep -q 'it was disabled' <<<\"\$out\" && grep -q 'TEMPLATES_DIR=\"\$HOME/Templates\"' '$HOME/.config/user-dirs.dirs'"
check "other user dirs kept" "grep -q XDG_DESKTOP_DIR '$HOME/.config/user-dirs.dirs'"
check "nothing written to home root" "[[ \$(count '$HOME') == 0 ]]"
mkdir -p "$HOME/Modelli"
printf 'XDG_TEMPLATES_DIR="$HOME/Modelli"\n' > "$HOME/.config/user-dirs.dirs"
bt install >/dev/null
check "localized folder honoured" "[[ \$(count '$HOME/Modelli') == 13 ]]"
check "old folder pruned" "[[ \$(count '$T') == 0 ]]"
printf 'XDG_TEMPLATES_DIR="$HOME/Templates"\n' > "$HOME/.config/user-dirs.dirs"
bt install >/dev/null

echo "== foreign files and uninstall =="
bt uninstall >/dev/null
echo "theirs" > "$T/Text Document.txt"
out=$(bt install)
check "foreign same-name file untouched" "grep -q 'skipped    Text Document.txt' <<<\"\$out\" && [[ \$(cat '$T/Text Document.txt') == theirs ]]"
echo "edited" >> "$T/Python Script.py"
"$PKG/uninstall.sh" >/dev/null
check "uninstall keeps edited + foreign" "[[ -f '$T/Python Script.py' && -f '$T/Text Document.txt' && \$(count '$T') == 2 ]]"
check "extension removed" "[[ ! -e '$HOME/.local/share/nautilus-python/extensions/right_click_new.py' ]]"
"$PKG/uninstall.sh" --force >/dev/null
check "--force removes edited only" "[[ ! -e '$T/Python Script.py' && -f '$T/Text Document.txt' ]]"
check "manifest gone" "[[ ! -e '$HOME/.local/share/right-click-new/manifest.json' ]]"

exit $fail
