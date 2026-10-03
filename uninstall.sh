#!/usr/bin/env bash
# Remove everything install.sh added.
#   ./uninstall.sh          keeps templates you edited
#   ./uninstall.sh --force  removes those too (a backup copy is kept)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/right-click-new"
EXT_DIR="$DATA_HOME/nautilus-python/extensions"

python3 "$HERE/build_templates.py" uninstall "$@"

rm -f "$EXT_DIR/right_click_new.py" "$EXT_DIR"/__pycache__/right_click_new.*.pyc
rmdir "$EXT_DIR/__pycache__" 2>/dev/null || true
rm -f "$APP_DIR/new-shortcut"
rmdir "$APP_DIR" 2>/dev/null || true

if [[ -d "$APP_DIR/backup" ]]; then
  echo "Backups of replaced or edited templates are in $APP_DIR/backup"
fi
echo "Removed \"New Shortcut…\". Run 'nautilus -q' to drop it from open Files windows."
