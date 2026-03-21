#!/usr/bin/env bash
set -euo pipefail

echo "Checking PR checks before merge..."
gh pr checks

echo
echo "Squash merging into base branch..."
gh pr merge --squash --delete-branch
