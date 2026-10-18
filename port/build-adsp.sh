#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-adsp.exit' EXIT
test ! -d out/kernel-adsp
test -f out/checkpoint-unattended-v5-build/Image
root=$PWD
src="$root/kernel"
out="$root/out/kernel-memory"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
python3 port/prepare-adsp.py
cp port/sm8750-lenovo-tb378fc-adsp.dts "$src/arch/arm64/boot/dts/qcom/"
"$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" port/tb378fc-adsp.config
make -C "$src" O="$out" olddefconfig
for config in CONFIG_ZRAM=y CONFIG_QCOM_Q6V5_PAS=y CONFIG_QCOM_PMIC_GLINK=y CONFIG_BATTERY_QCOM_BATTMGR=y; do
    grep -Fxq "$config" "$out/.config"
done
make -C "$src" O="$out" -j4 Image qcom/sm8750-lenovo-tb378fc-adsp.dtb
python3 - <<'PY'
from pathlib import Path
import shutil,hashlib,json
dest=Path('out/kernel-adsp');(dest/'arch/arm64/boot/dts/qcom').mkdir(parents=True)
for name in ['arch/arm64/boot/Image','.config','arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-adsp.dtb']:
 shutil.copy2(Path('out/kernel-memory')/name,dest/name)
manifest=json.loads(Path('out/keys-build.json').read_text())
manifest['status']='NATIVE_ADSP_AND_BATTERY_FOUNDATION_BUILD_ONLY_NOT_BOOTED'
files=['out/kernel-adsp/arch/arm64/boot/Image','out/kernel-adsp/.config',
       'out/kernel-adsp/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-adsp.dtb',
       'port/sm8750-lenovo-tb378fc-adsp.dts','port/prepare-adsp.py','port/build-adsp.sh',
       'port/tb378fc-adsp.config','port/fix-display-iova.py',
       'kernel/drivers/gpu/drm/msm/msm_kms.c','kernel/drivers/remoteproc/qcom_q6v5_pas.c']
for name in files:
 p=Path(name);manifest['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/adsp-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
python3 reference-tools/build-erhai-abl-symbols.py \
    --mainline-dtb out/kernel-adsp/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-adsp.dtb \
    --dtbo-img inputs/dtbo.img --base-dir inputs/stock-base --identity-index 11 \
    --dtc out/kernel-memory/scripts/dtc/dtc --output out/abl-adsp
echo NATIVE_ADSP_FOUNDATION_BUILD_PASSED_NOT_DEVICE_TESTED
