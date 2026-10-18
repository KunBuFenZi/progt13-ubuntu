#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-cpufreq.exit' EXIT
test ! -d out/kernel-cpufreq
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
kernel/scripts/kconfig/merge_config.sh -m -O out/kernel-memory out/kernel-audio-gated/.config port/tb378fc-cpufreq.config
make -C kernel O="$PWD/out/kernel-memory" olddefconfig
for option in CONFIG_QCOM_CPUCP_MBOX=y CONFIG_ARM_SCMI_CPUFREQ=y CONFIG_CPU_FREQ_DEFAULT_GOV_SCHEDUTIL=y; do
    grep -Fxq "$option" out/kernel-memory/.config
done
make -C kernel O="$PWD/out/kernel-memory" -j4 Image
mkdir -p out/kernel-cpufreq/arch/arm64/boot
cp out/kernel-memory/arch/arm64/boot/Image out/kernel-cpufreq/arch/arm64/boot/
cp out/kernel-memory/.config out/kernel-cpufreq/.config
python3 - <<'PY'
import hashlib,json
from pathlib import Path
m=json.loads(Path('out/audio-desktop-v4-build.json').read_text())
m['status']='CPUCP_SCMI_CPUFREQ_BUILT_NOT_DEVICE_TESTED'
for name in ['out/kernel-cpufreq/arch/arm64/boot/Image','out/kernel-cpufreq/.config',
             'port/build-cpufreq.sh','port/tb378fc-cpufreq.config','port/cpu-probe-init',
             'kernel/drivers/mailbox/qcom-cpucp-mbox.c']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/cpufreq-build.json').write_text(json.dumps(m,indent=2)+'\n')
PY
