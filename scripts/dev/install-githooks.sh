#!/usr/bin/env bash
set -Eeuo pipefail
git config core.hooksPath .githooks
echo "OK: configured core.hooksPath -> .githooks"
