#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
root=$PWD
src="$root/kernel"
out="$root/out/kernel-display"
test "$(git -C "$src" rev-parse HEAD)" = 958a2b4654196bb52dfa0217a0f65ffeaa919f81
python3 port/install-display-drivers.py
python3 port/enable-display-splash.py
python3 port/enable-dsi-lifecycle.py
python3 port/enable-dsi-diagnostics.py
python3 port/enable-dsi-vbif.py
cp port/sm8750-lenovo-tb378fc{,-display}.dts "$src/arch/arm64/boot/dts/qcom/"
if [ ! -d "$out" ]; then
    cp -a --reflink=auto "$root/out/kernel-stage1" "$out"
fi
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
"$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" port/tb378fc-display.config
make -C "$src" O="$out" olddefconfig
for config in CONFIG_DRM=y CONFIG_DRM_MSM=y CONFIG_DRM_MSM_DSI=y \
    CONFIG_DRM_PANEL_TB378FC_NT36526=y CONFIG_BACKLIGHT_TB378FC_AW99706B=y \
    CONFIG_REGULATOR_TB378FC_BIAS=y CONFIG_USB_CONFIGFS_RNDIS=y; do
    grep -Fxq "$config" "$out/.config"
done
make -C "$src" O="$out" -j4 qcom/sm8750-lenovo-tb378fc-display.dtb \
    drivers/gpu/drm/panel/panel-novatek-nt36526.o \
    drivers/video/backlight/tb378fc-aw99706b.o \
    drivers/regulator/tb378fc-panel-bias.o
echo DISPLAY_OBJECTS_AND_DTB_PASSED
make -C "$src" O="$out" -j4 Image
python3 - <<'PY'
from pathlib import Path
import hashlib,json
paths = ['out/kernel-display/arch/arm64/boot/Image',
         'out/kernel-display/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-display.dtb',
         'out/kernel-display/.config', 'port/tb378fc-display.config',
         'port/panel-novatek-nt36526.c', 'port/tb378fc-aw99706b.c',
         'port/tb378fc-panel-bias.c', 'port/sm8750-lenovo-tb378fc-display.dts',
         'port/enable-display-splash.py', 'out/display-splash.patch',
         'port/enable-dsi-lifecycle.py', 'out/display-dsi-lifecycle.patch',
         'port/enable-dsi-diagnostics.py', 'out/display-dsi-diagnostics.patch',
         'port/enable-dsi-vbif.py', 'out/display-dsi-vbif.patch',
         'port/sm8750-lenovo-tb378fc.dts']
Path('out/display-build.json').write_text(json.dumps({
    'status':'BUILD_ONLY_NOT_HARDWARE_TESTED',
    'kernel_commit':'958a2b4654196bb52dfa0217a0f65ffeaa919f81',
    'files':{p:{'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                'size':Path(p).stat().st_size} for p in paths}},indent=2)+'\n')
PY
echo DISPLAY_KERNEL_BUILD_PASSED
