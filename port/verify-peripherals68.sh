#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
root="$PWD"
work="$root/out/peripherals-verify68"
mkdir "$work"
mkdir "$work/upper" "$work/work" "$work/root"
unshare --mount bash -euo pipefail -c '
    root=$1;work=$2
    mount --make-rprivate /
    mount -t overlay overlay -o "lowerdir=$root/out/desktop-root,upperdir=$work/upper,workdir=$work/work" "$work/root"
    trap '\''umount "$work/root"'\'' EXIT
    tar -xf "$root/out/peripherals-package68d/settings.tar" -C "$work/root"
    systemd-analyze --root="$work/root" verify tb378fc-runtime68.service tb378fc-sensors-rpcd.service iio-sensor-proxy.service tb378fc-power-key.service >"$work/units.log" 2>&1
    printf "UNIT_GRAPH_VERIFIED\n"
' sh "$root" "$work"
