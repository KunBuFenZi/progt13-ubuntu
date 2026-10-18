#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
root=$PWD
src="$root/kernel"
out="$root/out/kernel-memory"
test ! -d "$out"
python3 port/fix-display-iova.py
cp -a --reflink=auto out/kernel-wifi "$out"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
"$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" port/tb378fc-memory.config
make -C "$src" O="$out" olddefconfig
for config in CONFIG_ZRAM=y CONFIG_ZSMALLOC=y CONFIG_ZRAM_BACKEND_LZ4=y CONFIG_PSI=y; do
    grep -Fxq "$config" "$out/.config"
done
make -C "$src" O="$out" -j2 Image
grep -aq 'KMS IOVA aperture' "$out/arch/arm64/boot/Image"
python3 - <<'PY'
from pathlib import Path
import hashlib,json
manifest=json.loads(Path('out/keys-build.json').read_text())
manifest['status']='ZRAM_BUILD_ONLY_NOT_DEVICE_TESTED'
for p in ['out/kernel-memory/arch/arm64/boot/Image','out/kernel-memory/.config',
          'port/tb378fc-memory.config','port/build-memory.sh','port/fix-display-iova.py',
          'kernel/drivers/gpu/drm/msm/msm_kms.c']:
 manifest['files'][p]={'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),'size':Path(p).stat().st_size}
Path('out/memory-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
echo MEMORY_KERNEL_BUILD_PASSED
