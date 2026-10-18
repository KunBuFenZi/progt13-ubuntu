#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/finish-live-audio66.exit' EXIT
while kill -0 1544416 2>/dev/null; do
    test ! -e logs/build-live-audio-kernel66.exit || break
    sleep 10
done
test "$(cat logs/build-live-audio-kernel66.exit)" = 0
bash port/build-live-audio-modules66.sh
python3 port/package-live-audio66.py
