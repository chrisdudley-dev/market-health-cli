#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:?export REPO=OWNER/REPO first}"

echo "Repo:   $REPO"
echo "Branch: $(git branch --show-current)"
echo

echo "PR status:"
gh pr status --repo "$REPO" || true
echo

echo "PR checks:"
set +e
gh pr checks --repo "$REPO"
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
  echo
  echo "CI is green."
elif [ "$rc" -eq 8 ]; then
  echo
  echo "CI is still pending."
  run_id="$(gh run list --repo "$REPO" --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')"
  if [ -n "${run_id:-}" ] && [ "$run_id" != "null" ]; then
    gh run watch --repo "$REPO" "$run_id" --compact
  else
    echo "No workflow run found for this branch yet."
  fi
else
  echo
  echo "CI has failures or no PR is connected yet."
  exit "$rc"
fi
