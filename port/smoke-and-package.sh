#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
set +e
timeout 50 qemu-system-aarch64 -M virt -cpu max -m 1024 -smp 2 \
    -display none -serial stdio -monitor none -no-reboot \
    -kernel out/kernel-stage1/arch/arm64/boot/Image \
    -initrd out/initramfs-stage1/initramfs.cpio.gz \
    -append 'console=ttyAMA0 rdinit=/init panic=15 loglevel=7' \
    >logs/qemu-stage1.log 2>&1
rc=$?
set -e
test "$rc" -eq 124
grep -Fq TB378FC_STAGE1_INIT_STARTED logs/qemu-stage1.log
if grep -Eq 'Kernel panic|Oops:|Unable to handle kernel' logs/qemu-stage1.log; then
    echo QEMU_SMOKE_FAILED
    exit 1
fi
echo QEMU_RAM_INIT_SMOKE_PASSED
python3 port/package-stage1.py >logs/package-stage1.log 2>&1
echo STAGE1_CANDIDATE_READY
