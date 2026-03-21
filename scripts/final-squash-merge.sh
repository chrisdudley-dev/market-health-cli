#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:?export REPO=OWNER/REPO first}"
BRANCH="$(git branch --show-current)"

echo "Checking PR checks before merge..."
gh pr checks "$BRANCH" --repo "$REPO"

echo
echo "Squash merging into base branch..."
gh pr merge "$BRANCH" --repo "$REPO" --squash --delete-branch
