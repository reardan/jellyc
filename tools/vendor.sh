#!/bin/sh
# Fetch the reference Jelly interpreter (stage0) at the pinned commit.
# The interpreter is pure Python; its only third-party dependency is sympy.
set -eu

PIN=70c9fd93ab009c05dc396f8cc091f72b212fb188
REPO=https://github.com/DennisMitchell/jellylanguage.git
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/vendor/jellylanguage"

if [ -d "$DEST/.git" ]; then
    HAVE="$(git -C "$DEST" rev-parse HEAD)"
    if [ "$HAVE" = "$PIN" ]; then
        echo "vendor: jellylanguage already pinned at $PIN"
        exit 0
    fi
    git -C "$DEST" fetch -q origin "$PIN"
    git -C "$DEST" checkout -q "$PIN"
else
    git clone -q "$REPO" "$DEST"
    git -C "$DEST" checkout -q "$PIN"
fi
echo "vendor: jellylanguage pinned at $PIN"

python3 -c 'import sympy' 2>/dev/null || python3 -m pip install sympy
