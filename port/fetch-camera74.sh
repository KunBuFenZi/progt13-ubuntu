#!/bin/sh
set -eu
cd "$(dirname -- "$0")/.."
camera74_tree=out/reference-camera74/kernel
test ! -e "$camera74_tree"
git init "$camera74_tree"
git -C "$camera74_tree" remote add origin https://github.com/h0cheung/tb322fc-linux-kernel.git
git -C "$camera74_tree" config remote.origin.promisor true
git -C "$camera74_tree" config remote.origin.partialclonefilter blob:none
git -C "$camera74_tree" fetch --depth=1 --filter=blob:none origin bf96c3d4048973298ede78487177c6f1b4f6bc0f
git -C "$camera74_tree" sparse-checkout init --no-cone
git -C "$camera74_tree" sparse-checkout set --no-cone \
    /drivers/media/platform/qcom/camss/ \
    /drivers/media/i2c/gc08a8.c \
    /drivers/media/i2c/ov13b10.c \
    /drivers/media/i2c/gt9772b.c \
    /drivers/i2c/busses/i2c-qcom-cci.c \
    /arch/arm64/boot/dts/qcom/sm8750.dtsi \
    /arch/arm64/boot/dts/qcom/sm8750-lenovo-elden.dts \
    /drivers/clk/qcom/cambistmclkcc-sm8750.c \
    /drivers/clk/qcom/camcc-sm8750.c
git -C "$camera74_tree" checkout --detach FETCH_HEAD
test "$(git -C "$camera74_tree" rev-parse HEAD)" = bf96c3d4048973298ede78487177c6f1b4f6bc0f
git -C "$camera74_tree" status --porcelain
