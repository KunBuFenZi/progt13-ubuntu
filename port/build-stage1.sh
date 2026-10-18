#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
src="$root/kernel"
out="$root/out/kernel-stage1"
expected=958a2b4654196bb52dfa0217a0f65ffeaa919f81
test "$(git -C "$src" rev-parse HEAD)" = "$expected"
test ! -e "$src/.git/index.lock"
cp "$root/port/sm8750-lenovo-tb378fc.dts" "$src/arch/arm64/boot/dts/qcom/"
mkdir -p "$out"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC'
export KBUILD_BUILD_VERSION=1
make -C "$src" O="$out" defconfig
"$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" \
    "$src/arch/arm64/configs/erhai-firstboot.config" "$root/port/tb378fc-stage1.config"
make -C "$src" O="$out" olddefconfig
for setting in CONFIG_USB_DWC3=y CONFIG_USB_DWC3_QCOM=y CONFIG_PHY_QCOM_M31_EUSB=y \
    CONFIG_PHY_QCOM_EUSB2_REPEATER=y CONFIG_USB_CONFIGFS=y CONFIG_USB_CONFIGFS_ACM=y \
    CONFIG_USB_CONFIGFS_NCM=y CONFIG_GUNYAH_WATCHDOG=y CONFIG_REGULATOR_QCOM_RPMH=y; do
    grep -Fxq "$setting" "$out/.config" || { echo "Missing $setting"; exit 1; }
done
make -C "$src" O="$out" -j4 qcom/sm8750-lenovo-tb378fc.dtb
fdtget -p "$out/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc.dtb" /chosen >/dev/null
printf 'DEVICE_TREE_COMPILE_PASSED\n'
make -C "$src" O="$out" -j4 Image
python3 - "$root" "$expected" <<'PY'
import hashlib, json, pathlib, sys
root, commit = pathlib.Path(sys.argv[1]), sys.argv[2]
files = ['out/kernel-stage1/arch/arm64/boot/Image',
         'out/kernel-stage1/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc.dtb',
         'out/kernel-stage1/.config', 'port/sm8750-lenovo-tb378fc.dts',
         'port/tb378fc-stage1.config', 'kernel/arch/arm64/configs/erhai-firstboot.config']
manifest = {'status': 'OFFLINE_BUILD_NOT_BOOT_TESTED', 'kernel_commit': commit,
            'board': 'lenovo,tb378fc', 'scope': 'RAM diagnostic kernel, USB2 peripheral',
            'files': {name: {'sha256': hashlib.sha256((root/name).read_bytes()).hexdigest(),
                             'size': (root/name).stat().st_size} for name in files}}
(root/'out/stage1-build.json').write_text(json.dumps(manifest, indent=2)+'\n')
print('STAGE1_KERNEL_BUILD_PASSED')
PY
