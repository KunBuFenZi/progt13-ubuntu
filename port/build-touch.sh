#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
root=$PWD
src="$root/kernel"
variant=${TB378FC_VARIANT:-touch}
case "$variant" in touch|gpu) ;; *) exit 2 ;; esac
out="$root/out/kernel-$variant"
test "$(git -C "$src" rev-parse HEAD)" = 958a2b4654196bb52dfa0217a0f65ffeaa919f81
python3 port/enable-tb378fc-touch.py
if [ ! -d "$out" ]; then
    baseline="$root/out/kernel-display"
    [ "$variant" != gpu ] || baseline="$root/out/kernel-touch"
    cp -a --reflink=auto "$baseline" "$out"
fi
cp port/sm8750-lenovo-tb378fc{,-display,-touch}.dts "$src/arch/arm64/boot/dts/qcom/"
[ "$variant" != gpu ] || cp port/sm8750-lenovo-tb378fc-gpu.dts "$src/arch/arm64/boot/dts/qcom/"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
"$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" port/tb378fc-touch.config
if [ "$variant" = gpu ]; then
    "$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" port/tb378fc-gpu.config
fi
make -C "$src" O="$out" olddefconfig
for config in CONFIG_SPI_QCOM_GENI=y CONFIG_TOUCHSCREEN_NT36536_SPI=y CONFIG_INPUT_EVDEV=y; do
    grep -Fxq "$config" "$out/.config"
done
make -C "$src" O="$out" -j4 "qcom/sm8750-lenovo-tb378fc-$variant.dtb" Image
python3 - "$variant" <<'PY'
from pathlib import Path
import hashlib,json,sys
variant=sys.argv[1]
paths = [f'out/kernel-{variant}/arch/arm64/boot/Image',
         f'out/kernel-{variant}/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-{variant}.dtb',
         f'out/kernel-{variant}/.config','port/sm8750-lenovo-tb378fc-touch.dts',
         'port/tb378fc-touch.config','port/enable-tb378fc-touch.py','out/tb378fc-touch.patch']
if variant=='gpu':paths += ['port/sm8750-lenovo-tb378fc-gpu.dts','port/tb378fc-gpu.config']
Path(f'out/{variant}-build.json').write_text(json.dumps({'status':'BUILD_ONLY_NOT_HARDWARE_TESTED',
 'kernel_commit':'958a2b4654196bb52dfa0217a0f65ffeaa919f81',
 'display_baseline':'out/checkpoint-display-good/display-build.json',
 'files':{p:{'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),
             'size':Path(p).stat().st_size} for p in paths}},indent=2)+'\n')
PY
echo "${variant^^}_KERNEL_BUILD_PASSED"
