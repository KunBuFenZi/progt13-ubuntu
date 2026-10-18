#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/package-unattended.exit' EXIT
for attempt in $(seq 1 180); do
    if [ -f logs/build-memory.exit ]; then break; fi
    sleep 10
done
test "$(cat logs/build-memory.exit)" = 0
python3 port/package-wireless-desktop.py \
    --output out/boot-unattended-v4 \
    --image-name boot-tb378fc-unattended-v4.img \
    --initramfs-output out/initramfs-unattended-v4 \
    --kernel out/kernel-memory/arch/arm64/boot/Image \
    --build-manifest out/memory-build.json --zram \
    --usb-ssh-runtime out/usb-ssh-runtime.tar \
    --usb-ssh-public-key out/device-ssh/id_ed25519.pub
