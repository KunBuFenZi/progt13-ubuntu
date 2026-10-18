#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-aw88480.exit' EXIT
test ! -d out/kernel-aw88480
python3 port/prepare-aw88480.py
python3 port/fix-audioreach-startup.py
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
kernel/scripts/kconfig/merge_config.sh -m -O out/kernel-memory out/kernel-audio-foundation/.config port/tb378fc-aw88480.config
make -C kernel O="$PWD/out/kernel-memory" olddefconfig
grep -Fxq CONFIG_SND_SOC_AW88480=y out/kernel-memory/.config
make -C kernel O="$PWD/out/kernel-memory" -j4 Image qcom/sm8750-lenovo-tb378fc-audio-probe.dtb
mkdir -p out/kernel-aw88480/arch/arm64/boot/dts/qcom
cp out/kernel-memory/arch/arm64/boot/Image out/kernel-aw88480/arch/arm64/boot/
cp out/kernel-memory/.config out/kernel-aw88480/.config
cp out/kernel-memory/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio-probe.dtb out/kernel-aw88480/arch/arm64/boot/dts/qcom/
python3 - <<'PY'
import hashlib,json
from pathlib import Path
m=json.loads(Path('out/audio-foundation-package-build.json').read_text())
m['status']='NATIVE_AW88480_CODEC_ENUMERATION_BUILT_NOT_DEVICE_TESTED'
files=['out/kernel-aw88480/arch/arm64/boot/Image','out/kernel-aw88480/.config',
       'out/kernel-aw88480/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio-probe.dtb',
       'port/aw88480.c','port/prepare-native-audio.py','port/prepare-aw88480.py',
       'port/build-aw88480.sh','port/fix-audioreach-startup.py','port/build-initramfs.py',
       'port/tb378fc-aw88480.config','port/sm8750-lenovo-tb378fc-audio-probe.dts',
       'out/audio-native/aw88480-native-music.acf',
       'kernel/sound/soc/codecs/aw88480.c','kernel/sound/soc/codecs/Kconfig',
       'kernel/sound/soc/codecs/Makefile','kernel/sound/soc/qcom/qdsp6/q6apm.c']
for name in files:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/aw88480-build.json').write_text(json.dumps(m,indent=2)+'\n')
PY
python3 reference-tools/build-erhai-abl-symbols.py \
    --mainline-dtb out/kernel-aw88480/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio-probe.dtb \
    --dtbo-img inputs/dtbo.img --base-dir inputs/stock-base --identity-index 11 \
    --dtc out/kernel-memory/scripts/dtc/dtc --output out/abl-aw88480
