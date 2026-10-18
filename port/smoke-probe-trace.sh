#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
set +e
timeout 25 qemu-system-aarch64 -M virt -cpu max -m 1024 -smp 2 \
    -display none -serial stdio -monitor none -no-reboot \
    -kernel out/kernel-stage1/arch/arm64/boot/Image \
    -initrd out/initramfs-stage1/initramfs.cpio.gz \
    -append 'console=ttyAMA0 rdinit=/init panic=15 initcall_debug ignore_loglevel' \
    >logs/qemu-probe-trace.log 2>&1
rc=$?
set -e
test "$rc" -eq 124
for marker in TB378FC_STAGE1_INIT_STARTED 'TBPROBE B' 'TBPROBE E'; do
    grep -Fq "$marker" logs/qemu-probe-trace.log
done
if grep -Eq 'Kernel panic|Oops:|Unable to handle kernel' logs/qemu-probe-trace.log; then
    echo PROBE_TRACE_SMOKE_FAILED
    exit 1
fi
echo PROBE_TRACE_RAM_INIT_SMOKE_PASSED
