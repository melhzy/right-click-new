#!/usr/bin/env bash
# Run linters and every test. Used by CI; run it locally the same way:
#   pip install -r tests/requirements.txt && tests/run_all.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
status=0
run() { echo; echo "### $*"; "$@" || status=1; }

run python3 -m pyflakes build_templates.py bin/new-shortcut nautilus/right_click_new.py tests/*.py
if command -v shellcheck >/dev/null; then
  run shellcheck install.sh uninstall.sh tests/*.sh
else
  echo "(shellcheck not installed - skipped)"
fi
run python3 tests/validate_templates.py
run bash tests/test_install.sh
run bash tests/test_shortcut.sh
run python3 tests/test_extension.py

echo
if ((status)); then echo "SOME CHECKS FAILED"; else echo "ALL CHECKS PASSED"; fi
exit $status
