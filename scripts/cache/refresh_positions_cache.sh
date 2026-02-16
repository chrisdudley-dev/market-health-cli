#!/usr/bin/env bash
set -Eeuo pipefail

# Repo root from this file location
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PY="./.venv/bin/python"
if [ ! -x "$PY" ]; then PY="python3"; fi

SCHWAB_JSON=""
CSV=""
OUT=""
PASSTHRU=()

while [ $# -gt 0 ]; do
  case "$1" in
    --schwab-json)
      SCHWAB_JSON="${2:-}"; shift 2;;
    --csv)
      CSV="${2:-}"; shift 2;;
    --out)
      OUT="${2:-}"; shift 2;;
    *)
      PASSTHRU+=("$1"); shift;;
  esac
done

if [ -z "$OUT" ]; then OUT="${HOME}/.cache/jerboa/positions.v1.json"; fi

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

_postprocess_positions_json() {
  local outp="$1"; shift
  local label="$1"; shift
  local input_path="${1:-}"; shift || true
  local broker="${1:-}"; shift || true
  "$PY" - "$outp" "$label" "$input_path" "$broker" <<'PY'
import hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

outp = Path(sys.argv[1])
label = sys.argv[2]
input_path = sys.argv[3] if len(sys.argv) > 3 else ""
broker = sys.argv[4] if len(sys.argv) > 4 else ""

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

doc = json.loads(outp.read_text())
if not isinstance(doc, dict):
    raise SystemExit("ERR: positions JSON is not an object")

doc["schema"] = "positions.v1"
if doc.get("asof"):
    doc["generated_at"] = doc["asof"]
else:
    doc.setdefault("generated_at", iso_now())

src = doc.get("source")
if not isinstance(src, dict):
    src = {}

src.setdefault("type", label.replace("_", "-"))
src.setdefault("method", label)
if broker:
    src.setdefault("broker", broker)

if input_path:
    p = Path(os.path.expanduser(input_path))
    src.setdefault("path", str(p))
    if p.exists():
        st = p.stat()
        src["file_mtime"] = iso_from_ts(st.st_mtime)
        src["file_size"] = int(st.st_size)
        try:
            src["file_sha256"] = sha256_file(p)
        except Exception:
            pass
        doc.setdefault("asof", src.get("file_mtime"))

doc["source"] = src
outp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
PY
}

_commit_if_changed() {
  local tmp_out="$1"; shift
  local out="$1"; shift
  mkdir -p "$(dirname "$out")"
  if [ -f "$out" ] && cmp -s "$tmp_out" "$out"; then
    rm -f "$tmp_out" || true
    echo "OK: positions unchanged; not rewriting"
    return 0
  fi
  mv -f "$tmp_out" "$out"
  chmod 600 "$out" 2>/dev/null || true
  echo "OK: wrote positions -> $out"
  return 0
}

mkdir -p "$(dirname "$OUT")"

if [ -n "$SCHWAB_JSON" ]; then
  tmp_out="$(mktemp "${OUT}.tmp.XXXXXX")"
  _run "schwab_json" "$PY" scripts/import_positions_schwab_json.py --in "$SCHWAB_JSON" --out "$tmp_out"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    rm -f "$tmp_out" || true
    exit "$rc"
  fi
  _postprocess_positions_json "$tmp_out" "schwab_json" "$SCHWAB_JSON" "schwab"
  _commit_if_changed "$tmp_out" "$OUT"
  exit 0
fi

tmp_out="$(mktemp "${OUT}.tmp.XXXXXX")"
args=()
if [ -n "$CSV" ]; then args+=(--csv "$CSV"); fi

_run "tos_csv" "$PY" scripts/import_positions_tos_csv.py "${args[@]}" "${PASSTHRU[@]}" --out "$tmp_out"
rc=$?
if [ "$rc" -ne 0 ]; then
  rm -f "$tmp_out" || true
  exit "$rc"
fi

_postprocess_positions_json "$tmp_out" "tos_csv" "$CSV" "thinkorswim"
_commit_if_changed "$tmp_out" "$OUT"
exit 0
