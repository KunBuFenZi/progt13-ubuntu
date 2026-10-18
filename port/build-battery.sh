#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-battery.exit' EXIT
variant=""
extra=()
if [ "${1:-}" = current ]; then variant=-v2; extra=(--correct-current); fi
dest="out/kernel-battery$variant"
test ! -d "$dest"
python3 port/fix-lenovo-battery.py "${extra[@]}"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
cmp out/kernel-memory/.config out/kernel-adsp/.config
make -C kernel O="$PWD/out/kernel-memory" -j4 Image
mkdir -p "$dest/arch/arm64/boot"
cp out/kernel-memory/arch/arm64/boot/Image "$dest/arch/arm64/boot/"
cp out/kernel-memory/.config "$dest/.config"
python3 - "$variant" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path('out/adsp-build.json');m=json.loads(p.read_text())
m['status']='TB378FC_BATTERY_POWER_QUIRK_BUILT_NOT_DEVICE_TESTED'
variant=sys.argv[1]
for name in ['out/kernel-battery'+variant+'/arch/arm64/boot/Image','out/kernel-battery'+variant+'/.config',
             'kernel/drivers/power/supply/qcom_battmgr.c',
             'kernel/Documentation/devicetree/bindings/soc/qcom/qcom,pmic-glink.yaml',
             'port/fix-lenovo-battery.py','port/build-battery.sh']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/battery'+variant+'-build.json').write_text(json.dumps(m,indent=2)+'\n')
PY
