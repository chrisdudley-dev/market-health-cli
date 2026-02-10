#!/usr/bin/env bash
set -Eeuo pipefail

# Repo root from this file location
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PY="./.venv/bin/python"
if [ ! -x "$PY" ]; then PY="python3"; fi

SCHWAB_JSON=""
OUT=""
PASSTHRU=()

while [ $# -gt 0 ]; do
  case "$1" in
    --schwab-json)
      SCHWAB_JSON="${2:-}"; shift 2;;
    --out)
      OUT="${2:-}"; PASSTHRU+=("$1" "${2:-}"); shift 2;;
    *)
      PASSTHRU+=("$1"); shift;;
  esac
done

_fail_bundle() {
  local label="$1"; shift
  local tmpfile="$1"; shift
  local rc="$1"; shift
  local fail_dir="${HOME}/.cache/jerboa/failures"
  mkdir -p "$fail_dir"
  local out="${fail_dir}/positions_refresh.${label}.$(date +%Y%m%d-%H%M%S).log"
  {
    echo "time: $(date -Is)"
    echo "label: ${label}"
    echo "rc: ${rc}"
    echo "cwd: $(pwd)"
    echo "cmd: $*"
    echo
    echo "---- output ----"
    cat "$tmpfile" 2>/dev/null || true
    echo "---- end ----"
  } > "$out"
  echo "$out"
}

_run() {
  local label="$1"; shift
  local tmp
  tmp="$(mktemp)"
  set +e
  "$@" > >(tee "$tmp") 2> >(tee -a "$tmp" >&2)
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    bundle="$(_fail_bundle "$label" "$tmp" "$rc" "$@")"
    echo "ERR: positions refresh failed; bundle: $bundle" >&2
  fi
  rm -f "$tmp" || true
  return "$rc"
}

if [ -n "$SCHWAB_JSON" ]; then
  if [ -z "$OUT" ]; then OUT="${HOME}/.cache/jerboa/positions.v1.json"; fi
  _run "schwab_json" "$PY" scripts/import_positions_schwab_json.py --in "$SCHWAB_JSON" --out "$OUT"
  exit $?
fi

_run "tos_csv" "$PY" scripts/import_positions_tos_csv.py "${PASSTHRU[@]}"
