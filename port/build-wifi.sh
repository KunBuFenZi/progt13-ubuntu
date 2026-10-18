#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
root=$PWD
src="$root/kernel"
out="$root/out/kernel-wifi"
test "$(git -C "$src" rev-parse HEAD)" = 958a2b4654196bb52dfa0217a0f65ffeaa919f81
python3 port/prepare-wireless.py
if [ ! -d "$out" ]; then
    cp -a --reflink=auto out/kernel-desktop "$out"
fi
cp port/sm8750-lenovo-tb378fc{,-display,-touch,-gpu,-wifi}.dts "$src/arch/arm64/boot/dts/qcom/"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
"$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" port/tb378fc-wifi.config
make -C "$src" O="$out" olddefconfig
for config in CONFIG_PCI=y CONFIG_PCIE_QCOM=y CONFIG_ATH12K=y CONFIG_POWER_SEQUENCING_QCOM_WCN=y; do
    grep -Fxq "$config" "$out/.config"
done
make -C "$src" O="$out" -j2 qcom/sm8750-lenovo-tb378fc-wifi.dtb Image
python3 - <<'PY'
from pathlib import Path
import hashlib,json
paths=['out/kernel-wifi/arch/arm64/boot/Image',
       'out/kernel-wifi/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-wifi.dtb',
       'out/kernel-wifi/.config','port/tb378fc-wifi.config',
       'port/sm8750-lenovo-tb378fc-wifi.dts','port/prepare-wireless.py']
Path('out/wifi-build.json').write_text(json.dumps({
 'status':'BUILD_ONLY_NOT_HARDWARE_TESTED',
 'kernel_commit':'958a2b4654196bb52dfa0217a0f65ffeaa919f81',
 'baseline':'out/checkpoint-desktop-dual-good',
 'files':{p:{'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),
             'size':Path(p).stat().st_size} for p in paths}},indent=2)+'\n')
PY
echo WIFI_KERNEL_BUILD_PASSED
