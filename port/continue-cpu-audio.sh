#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/continue-cpu-audio.exit' EXIT
while pgrep -f '^bash port/build-cpufreq.sh$' >/dev/null; do
    sleep 10
done
test "$(cat logs/build-cpufreq.exit)" = 0
bash port/build-cpu-audio-ready.sh
python3 port/package-cpu-audio-ready.py
