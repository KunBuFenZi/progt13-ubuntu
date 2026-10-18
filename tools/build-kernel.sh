#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
src=${1:-"$root/out/kernel-source"}
build=${2:-"$root/out/kernel-base"}
test "$(git -C "$src" rev-parse HEAD)" = 958a2b4654196bb52dfa0217a0f65ffeaa919f81
mkdir -p "$build"
build=$(cd "$build" && pwd)
export ARCH=arm64 CROSS_COMPILE=${CROSS_COMPILE:-aarch64-linux-gnu-}
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
cp "$root/kernel/configs/base.config" "$build/.config"
make -C "$src" O="$build" LOCALVERSION=+ olddefconfig
make -C "$src" O="$build" LOCALVERSION=+ -j"${JOBS:-2}" Image
dtc -I dts -O dtb -o "$build/tb378fc-final.dtb" "$root/kernel/board/sm8750-lenovo-tb378fc-final.dts"
sha256sum "$build/arch/arm64/boot/Image" "$build/tb378fc-final.dtb"
echo 'Base kernel built. Build external runtime modules separately; see docs/BUILD.zh-CN.md.'
