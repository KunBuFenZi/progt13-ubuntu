#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
# The first compile is already running. Wait for it before updating its inputs.
while ps -p 653857 -o args= | grep -q '^bash port/build-stage1.sh$'; do
    sleep 5
done
exec >logs/finish-stage1.log 2>&1
test -f out/stage1-build.json
cp incoming/sm8750-lenovo-tb378fc.dts incoming/tb378fc-stage1.config port/
bash port/build-stage1.sh >logs/stage1-revision-build.log 2>&1
mv out/abl-stage1 out/abl-stage1-initial
python3 reference-tools/build-erhai-abl-symbols.py \
    --mainline-dtb out/kernel-stage1/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc.dtb \
    --base-dir inputs/stock-base --identity-base inputs/live-device-tree.dtb \
    --dtbo-img inputs/dtbo.img --dtc /usr/bin/dtc --output out/abl-stage1 \
    >logs/abl-stage1-final.log 2>&1
python3 port/check-stock-overlays.py >logs/overlay-check.log 2>&1
python3 port/build-initramfs.py >logs/initramfs-stage1.log 2>&1
bash port/smoke-and-package.sh
