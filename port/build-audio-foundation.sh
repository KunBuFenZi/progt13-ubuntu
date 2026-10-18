#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-audio-foundation.exit' EXIT
test ! -d out/kernel-audio-foundation
python3 port/prepare-audio-foundation.py
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
cmp out/kernel-memory/.config out/kernel-battery-v2/.config
kernel/scripts/kconfig/merge_config.sh -m -O out/kernel-memory out/kernel-memory/.config port/tb378fc-audio-foundation.config
make -C kernel O="$PWD/out/kernel-memory" olddefconfig
for config in CONFIG_SND_SOC_QDSP6=y CONFIG_QCOM_APR=y CONFIG_BATTERY_QCOM_BATTMGR=y CONFIG_ZRAM=y; do
    grep -Fxq "$config" out/kernel-memory/.config
done
make -C kernel O="$PWD/out/kernel-memory" -j4 Image
mkdir -p out/kernel-audio-foundation/arch/arm64/boot
cp out/kernel-memory/arch/arm64/boot/Image out/kernel-audio-foundation/arch/arm64/boot/
cp out/kernel-memory/.config out/kernel-audio-foundation/.config
python3 - <<'PY'
import hashlib,json
from pathlib import Path
m=json.loads(Path('out/battery-v2-build.json').read_text())
m['status']='AUDIOREACH_FOUNDATION_BUILT_NOT_DEVICE_TESTED'
for name in ['out/kernel-audio-foundation/arch/arm64/boot/Image','out/kernel-audio-foundation/.config',
             'kernel/sound/soc/qcom/qdsp6/q6apm.c','port/tb378fc-audio-foundation.config',
             'port/prepare-audio-foundation.py','port/build-audio-foundation.sh']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/audio-foundation-build.json').write_text(json.dumps(m,indent=2)+'\n')
PY
