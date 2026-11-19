#!/bin/sh
set -e
ROOT=$(git rev-parse --show-toplevel)
cp "$ROOT/security/pre-commit" "$ROOT/.git/hooks/pre-commit"
chmod +x "$ROOT/.git/hooks/pre-commit"
echo "pre-commit hook を導入しました"
