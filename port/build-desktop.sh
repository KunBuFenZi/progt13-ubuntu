#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
root=$PWD
src="$root/kernel"
out="$root/out/kernel-desktop"
test "$(git -C "$src" rev-parse HEAD)" = 958a2b4654196bb52dfa0217a0f65ffeaa919f81
if [ ! -d "$out" ]; then
    cp -a --reflink=auto out/kernel-gpu "$out"
fi
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
cp port/sm8750-lenovo-tb378fc{,-display,-touch,-gpu}.dts "$src/arch/arm64/boot/dts/qcom/"
cp port/tb378fc-aw99706b.c "$src/drivers/video/backlight/tb378fc-aw99706b.c"
"$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" port/tb378fc-desktop.config
make -C "$src" O="$out" olddefconfig
for config in CONFIG_SQUASHFS=y CONFIG_SQUASHFS_XZ=y CONFIG_SQUASHFS_ZSTD=y CONFIG_OVERLAY_FS=y CONFIG_CGROUPS=y CONFIG_FHANDLE=y; do
    grep -Fxq "$config" "$out/.config"
done
make -C "$src" O="$out" -j4 qcom/sm8750-lenovo-tb378fc-gpu.dtb Image
python3 - <<'PY'
from pathlib import Path
import hashlib,json
paths=['out/kernel-desktop/arch/arm64/boot/Image',
       'out/kernel-desktop/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-gpu.dtb',
       'out/kernel-desktop/.config','port/tb378fc-desktop.config',
       'port/tb378fc-aw99706b.c','port/sm8750-lenovo-tb378fc-display.dts',
       'port/sm8750-lenovo-tb378fc-touch.dts']
Path('out/desktop-build.json').write_text(json.dumps({
 'status':'BUILD_ONLY_NOT_HARDWARE_TESTED',
 'kernel_commit':'958a2b4654196bb52dfa0217a0f65ffeaa919f81',
 'baseline':'out/checkpoint-gpu-good/gpu-build.json',
 'files':{p:{'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),
             'size':Path(p).stat().st_size} for p in paths}},indent=2)+'\n')
PY
echo DESKTOP_KERNEL_BUILD_PASSED
