#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-display-reference-lifecycle.exit' EXIT
test ! -d out/kernel-display-reference-lifecycle
python3 - <<'PY'
import hashlib,subprocess
from pathlib import Path
p=Path('kernel/drivers/gpu/drm/msm/dsi/dsi_manager.c')
original=subprocess.check_output(['git','-C','kernel','show','HEAD:drivers/gpu/drm/msm/dsi/dsi_manager.c'])
assert hashlib.sha256(original).hexdigest()=='421cd74c832fd3bc3a843a59c4979a35139a9d747f97a26e5b433f683129ee93'
assert 'TB378FC_DSI_PREPARE_BEFORE_VIDEO' in p.read_text()
Path('out/dsi-manager-before-reference.c').write_bytes(p.read_bytes())
p.write_bytes(original)
PY
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
make -C kernel O="$PWD/out/kernel-memory" -j4 Image
mkdir -p out/kernel-display-reference-lifecycle/arch/arm64/boot
cp out/kernel-memory/arch/arm64/boot/Image out/kernel-display-reference-lifecycle/arch/arm64/boot/
cp out/kernel-memory/.config out/kernel-display-reference-lifecycle/.config
python3 - <<'PY'
import hashlib,json
from pathlib import Path
m=json.loads(Path('out/audio-late-identity-build.json').read_text())
m['status']='REFERENCE_DSI_LIFECYCLE_RESTORED_NOT_DEVICE_TESTED'
for name in ['kernel/drivers/gpu/drm/msm/dsi/dsi_manager.c',
             'port/build-display-reference-lifecycle.sh',
             'out/kernel-display-reference-lifecycle/arch/arm64/boot/Image',
             'out/kernel-display-reference-lifecycle/.config']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/display-reference-lifecycle-build.json').write_text(json.dumps(m,indent=2)+'\n')
PY
