#!/usr/bin/env bash
# Tests for bin/new-shortcut: command-line mode and the dialog flow with a
# scripted stand-in for zenity.
set -uo pipefail
PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
mkdir -p "$W/desk" "$W/data/GAINS run" "$W/fakebin"
echo x > "$W/data/report.pdf"
NS="$PKG/bin/new-shortcut"
fail=0
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi; }

echo "== command-line mode =="
python3 "$NS" "$W/desk" --target "$W/data/report.pdf" --name "Q3 report" >/dev/null
check "file link keeps extension" "[[ -L '$W/desk/Q3 report.pdf' && \$(readlink '$W/desk/Q3 report.pdf') == '$W/data/report.pdf' ]]"
python3 "$NS" "$W/desk" --target "$W/data/report.pdf" --name "Q3 report" >/dev/null
check "name clash -> (2)" "[[ -L '$W/desk/Q3 report (2).pdf' ]]"
python3 "$NS" "$W/desk" --target "$W/data/GAINS run" >/dev/null
check "folder link, default name" "[[ -L '$W/desk/GAINS run' && -d '$W/desk/GAINS run' ]]"
python3 "$NS" "$W/desk" --url "www.umassmed.edu" >/dev/null
check "url shortcut, default name" "grep -q 'url=https://www.umassmed.edu' '$W/desk/umassmed.edu.html'"
python3 "$NS" "$W/desk" --url "localhost:8888/lab" --name Jupyter >/dev/null
check "localhost gets http://" "grep -q 'url=http://localhost:8888/lab' '$W/desk/Jupyter.html'"
python3 "$NS" "$W/desk" --url 'https://example.org/?a=1&b=<x>' --name "../evil/name" >/dev/null
check "url escaped, name sanitised" "grep -q 'a=1&amp;b=&lt;x&gt;' '$W/desk/-evil-name.html'"
for bad in "javascript:alert(1)" "file:///etc/passwd" "not a url" "intranet"; do
  python3 "$NS" "$W/desk" --url "$bad" 2>/dev/null; rc=$?
  check "rejects '$bad'" "[[ $rc == 2 ]]"
done
python3 "$NS" "$W/desk" --target "$W/nope" 2>/dev/null; rc=$?
check "missing target -> error" "[[ $rc == 2 ]]"

echo "== dialog flow (scripted zenity) =="
cat > "$W/fakebin/zenity" <<'EOF'
#!/usr/bin/env bash
# Returns one scripted answer per call from $ZENITY_ANSWERS; "!" = Cancel.
printf '%s\n' "$@" >> "$ZENITY_ANSWERS.args"
[[ " $* " == *" --error "* ]] && exit 0
ans=$(head -n1 "$ZENITY_ANSWERS"); sed -i '1d' "$ZENITY_ANSWERS"
[[ "$ans" == "!" ]] && exit 1
printf '%s\n' "$ans"
EOF
chmod +x "$W/fakebin/zenity"
export PATH="$W/fakebin:$PATH" ZENITY_ANSWERS="$W/answers"

printf 'A folder\n%s\nMy data\n' "$W/data/GAINS run" > "$W/answers"
python3 "$NS" "$W/desk" >/dev/null
check "folder shortcut" "[[ -L '$W/desk/My data' ]]"
check "chooser opens in current folder" "grep -q -- '--filename=$W/desk/' '$W/answers.args' && grep -q -- '--directory' '$W/answers.args'"

printf 'A web address (URL)\nscholar.google.com\n\n' > "$W/answers"
python3 "$NS" "$W/desk" >/dev/null
check "blank name uses default" "[[ -f '$W/desk/scholar.google.com.html' ]]"

printf 'A file\n!\n' > "$W/answers"
before=$(find "$W/desk" -mindepth 1 | wc -l)
python3 "$NS" "$W/desk"; rc=$?
check "cancel creates nothing" "[[ $rc == 1 && \$(find '$W/desk' -mindepth 1 | wc -l) == $before ]]"

printf 'A web address (URL)\nnot a url at all\n' > "$W/answers"; : > "$W/answers.args"
python3 "$NS" "$W/desk" 2>/dev/null; rc=$?
check "bad url shows an error dialog" "[[ $rc == 2 ]] && grep -q -- '--error' '$W/answers.args'"

exit $fail
