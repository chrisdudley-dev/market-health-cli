#!/usr/bin/env bash
set -euo pipefail

BRANCH="$(git branch --show-current)"

echo "Repo:   ${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo current-repo)}"
echo "Branch: $BRANCH"
echo

echo "PR status:"
gh pr status || true
echo

echo "PR checks:"
set +e
gh pr checks
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
  echo
  echo "CI is green."
elif [ "$rc" -eq 8 ]; then
  echo
  echo "CI is still pending."
  run_id="$(gh run list --branch "$BRANCH" --limit 1 --json databaseId --jq '.[0].databaseId')"
  if [ -n "${run_id:-}" ] && [ "$run_id" != "null" ]; then
    gh run watch "$run_id" --compact
  else
    echo "No workflow run found for this branch yet."
  fi
else
  echo
  echo "CI has failures."
  exit "$rc"
fi
