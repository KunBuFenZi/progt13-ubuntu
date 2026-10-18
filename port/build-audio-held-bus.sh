#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-audio-held-bus.exit' EXIT
test ! -d out/kernel-audio-held-bus
cmp out/kernel-memory/.config out/kernel-cpu-audio-ready/.config
cp port/aw88480.c kernel/sound/soc/codecs/aw88480.c
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
make -C kernel O="$PWD/out/kernel-memory" -j4 Image
mkdir -p out/kernel-audio-held-bus/arch/arm64/boot
cp out/kernel-memory/arch/arm64/boot/Image out/kernel-audio-held-bus/arch/arm64/boot/
cp out/kernel-memory/.config out/kernel-audio-held-bus/.config
python3 - <<'PY'
import hashlib,json
from pathlib import Path
m=json.loads(Path('out/cpu-audio-ready-build.json').read_text())
m['status']='DIAGNOSTIC_HOLD_I2C_BEFORE_FIRST_AMP_ACCESS_NOT_TESTED'
for name in ['port/aw88480.c','kernel/sound/soc/codecs/aw88480.c',
             'port/build-audio-held-bus.sh','out/kernel-audio-held-bus/arch/arm64/boot/Image',
             'out/kernel-audio-held-bus/.config']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/audio-held-bus-build.json').write_text(json.dumps(m,indent=2)+'\n')
PY
