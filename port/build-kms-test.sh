#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
root=$PWD
make -C kernel O="$root/out/kernel-display" ARCH=arm64 -j4 \
    headers_install INSTALL_HDR_PATH="$root/out/display-uapi"
aarch64-linux-gnu-gcc -static -O2 -Wall -Wextra -Werror \
    -I "$root/out/display-uapi/include" port/kms-test.c -o out/kms-test
echo KMS_PROBE_BUILD_PASSED
