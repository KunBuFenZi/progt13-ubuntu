#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-audio.exit' EXIT
test ! -d out/kernel-audio
python3 port/prepare-aw88480.py
cp port/sm8750-lenovo-tb378fc-audio.dts kernel/arch/arm64/boot/dts/qcom/
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
kernel/scripts/kconfig/merge_config.sh -m -O out/kernel-memory out/kernel-aw88480/.config port/tb378fc-audio.config
make -C kernel O="$PWD/out/kernel-memory" olddefconfig
grep -Fxq CONFIG_SND_SOC_SC8280XP=y out/kernel-memory/.config
make -C kernel O="$PWD/out/kernel-memory" -j4 Image qcom/sm8750-lenovo-tb378fc-audio.dtb
mkdir -p out/kernel-audio/arch/arm64/boot/dts/qcom
cp out/kernel-memory/arch/arm64/boot/Image out/kernel-audio/arch/arm64/boot/
cp out/kernel-memory/.config out/kernel-audio/.config
cp out/kernel-memory/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb out/kernel-audio/arch/arm64/boot/dts/qcom/
python3 - <<'PY'
import hashlib,json
from pathlib import Path
m=json.loads(Path('out/aw88480-build.json').read_text())
m['status']='AUDIO_PLAYBACK_BUILT_NOT_DEVICE_TESTED'
for name in ['out/kernel-audio/arch/arm64/boot/Image','out/kernel-audio/.config',
             'out/kernel-audio/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb',
             'port/aw88480.c','port/build-audio.sh','port/tb378fc-audio.config',
             'port/sm8750-lenovo-tb378fc-audio.dts','port/Lenovo-TB378FC.m4',
             'port/build-initramfs.py','port/audio-test-init','port/audio-probe',
             'out/topology-tb378fc/Lenovo-TB378FC-tplg.bin']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/audio-build.json').write_text(json.dumps(m,indent=2)+'\n')
PY
python3 reference-tools/build-erhai-abl-symbols.py \
    --mainline-dtb out/kernel-audio/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb \
    --dtbo-img inputs/dtbo.img --base-dir inputs/stock-base --identity-index 11 \
    --dtc out/kernel-memory/scripts/dtc/dtc --output out/abl-audio
