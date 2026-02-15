#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TOKEN_FILE="${HOME}/.cache/jerboa/schwab.token.json"
RAW_ACCTNUM="${HOME}/.cache/jerboa/schwab.accountNumbers.json"
RAW_OUT="${HOME}/.cache/jerboa/schwab_accounts.live.json"
POS_OUT="${HOME}/.cache/jerboa/positions.v1.json"

if [ ! -f "$TOKEN_FILE" ]; then
  echo "ERR: token cache not found: $TOKEN_FILE"
  echo "Run: scripts/schwab_oauth_walkthrough.py"
  exit 2
fi

now="$(date +%s)"
exp="$(jq -r '.expires_at // 0' "$TOKEN_FILE")"
if [ "$exp" -le $((now + 60)) ]; then
  echo "ERR: access token is expired/near-expiry (expires_at=$exp)."
  echo "Run: scripts/schwab_oauth_walkthrough.py to re-auth."
  exit 2
fi

TOKEN="$(jq -r '.access_token' "$TOKEN_FILE")"
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "ERR: access_token missing from $TOKEN_FILE"
  exit 2
fi

mkdir -p "${HOME}/.cache/jerboa"
chmod 700 "${HOME}/.cache/jerboa" 2>/dev/null || true

# 1) Get account hashes
code="$(curl -sS -o "$RAW_ACCTNUM" -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  "https://api.schwabapi.com/trader/v1/accounts/accountNumbers" || true)"
if [ "$code" != "200" ]; then
  echo "ERR: accountNumbers HTTP $code"
  echo "Tip: your app/token may not have Trader API access enabled."
  exit 2
fi

AHASH="$(jq -r '..|.hashValue? // empty' "$RAW_ACCTNUM" | head -n 1)"
if [ -z "$AHASH" ]; then
  echo "ERR: no hashValue found in accountNumbers response"
  exit 2
fi

# 2) Fetch positions for one account
code="$(curl -sS -o "$RAW_OUT" -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  "https://api.schwabapi.com/trader/v1/accounts/${AHASH}?fields=positions" || true)"
if [ "$code" != "200" ]; then
  echo "ERR: accounts/{hash}?fields=positions HTTP $code"
  exit 2
fi
chmod 600 "$RAW_ACCTNUM" "$RAW_OUT" 2>/dev/null || true

# 3) Normalize into positions.v1.json using your existing pipeline
scripts/jerboa/bin/jerboa-market-health-positions-refresh --schwab-json "$RAW_OUT" --out "$POS_OUT"

# 4) Validate + show summary
python3 scripts/validate_positions_v1.py --path "$POS_OUT"
jq '{n: ((.positions//[])|length), asof, source:{broker:.source.broker, path:.source.path}}' "$POS_OUT"
