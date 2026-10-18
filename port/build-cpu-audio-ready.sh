#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-cpu-audio-ready.exit' EXIT
test ! -d out/kernel-cpu-audio-ready
cmp out/kernel-memory/.config out/kernel-cpufreq/.config
python3 port/gate-audioreach-platform.py
cp port/aw88480.c kernel/sound/soc/codecs/aw88480.c
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
make -C kernel O="$PWD/out/kernel-memory" -j4 Image
mkdir -p out/kernel-cpu-audio-ready/arch/arm64/boot
cp out/kernel-memory/arch/arm64/boot/Image out/kernel-cpu-audio-ready/arch/arm64/boot/
cp out/kernel-memory/.config out/kernel-cpu-audio-ready/.config
python3 - <<'PY'
import hashlib,json
from pathlib import Path
m=json.loads(Path('out/cpufreq-build.json').read_text())
m['status']='CPUCP_AND_PLATFORM_AUDIO_READY_BUILT_NOT_DEVICE_TESTED'
for name in ['port/aw88480.c','kernel/sound/soc/codecs/aw88480.c','out/kernel-cpu-audio-ready/arch/arm64/boot/Image','out/kernel-cpu-audio-ready/.config',
             'port/build-cpu-audio-ready.sh','port/gate-audioreach-platform.py',
             'port/cpu-audio-probe-init','kernel/sound/soc/qcom/qdsp6/q6apm.c',
             'kernel/sound/soc/qcom/qdsp6/q6apm-dai.c']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/cpu-audio-ready-build.json').write_text(json.dumps(m,indent=2)+'\n')
PY
