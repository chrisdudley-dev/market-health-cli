#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:?export REPO=OWNER/REPO first}"

echo "Checking PR checks before merge..."
gh pr checks --repo "$REPO"

echo
echo "Squash merging into base branch..."
gh pr merge --repo "$REPO" --squash --delete-branch
