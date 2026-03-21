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
  echo "CI is still pending. Watching until completion..."
  gh pr checks --watch
else
  echo
  echo "CI has failures."
  exit "$rc"
fi
