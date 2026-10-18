#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-live-audio-kernel66.exit' EXIT
test ! -e out/kernel-live-audio66
python3 port/fix-glink-live-unload.py
python3 - <<'PY'
from pathlib import Path
import hashlib,re
p=Path('kernel/drivers/gpu/drm/msm/dsi/dsi_manager.c')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='421cd74c832fd3bc3a843a59c4979a35139a9d747f97a26e5b433f683129ee93'
base=Path('out/module-audio-sdk65/.config').read_text()
assert 'CONFIG_SOUND=m' in base and 'CONFIG_SND_SOC=m' in base
assert 'CONFIG_QCOM_CPUCP_MBOX=m' in base
Path('out/kernel-memory/.config').write_text(base)
PY
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
make -C kernel O="$PWD/out/kernel-memory" LOCALVERSION=+ olddefconfig
cmp out/kernel-memory/.config out/module-audio-sdk65/.config
# Preserve the already validated eight-core SCMI CPU-frequency support.
kernel/scripts/kconfig/merge_config.sh -m -O out/kernel-memory \
    out/kernel-memory/.config port/tb378fc-cpufreq.config
make -C kernel O="$PWD/out/kernel-memory" LOCALVERSION=+ olddefconfig
for item in CONFIG_SOUND=m CONFIG_SND_SOC=m CONFIG_QCOM_CPUCP_MBOX=y CONFIG_ARM_SCMI_CPUFREQ=y; do
    grep -Fxq "$item" out/kernel-memory/.config
done
make -C kernel O="$PWD/out/kernel-memory" LOCALVERSION=+ -j4 Image
mkdir -p out/kernel-live-audio66/arch/arm64/boot
cp out/kernel-memory/arch/arm64/boot/Image out/kernel-live-audio66/arch/arm64/boot/
cp out/kernel-memory/.config out/kernel-live-audio66/.config
cp out/kernel-memory/vmlinux.symvers out/kernel-live-audio66/
python3 - <<'PY'
import hashlib,json
from pathlib import Path
paths=['out/kernel-live-audio66/arch/arm64/boot/Image','out/kernel-live-audio66/.config',
       'out/kernel-live-audio66/vmlinux.symvers','kernel/drivers/rpmsg/qcom_glink_native.c',
       'kernel/drivers/gpu/drm/msm/dsi/dsi_manager.c','port/build-live-audio-kernel66.sh',
       'port/fix-glink-live-unload.py']
manifest={'status':'MODULAR_AUDIO_AND_GLINK_UNLOAD_FIX_BUILT_NOT_DEVICE_TESTED',
          'kernel_commit':'958a2b4654196bb52dfa0217a0f65ffeaa919f81',
          'files':{p:{'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                      'size':Path(p).stat().st_size} for p in paths}}
Path('out/live-audio-kernel66-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
