#!/bin/sh
# Explicit GPU drawing test; the running desktop keeps its current renderer.
set -u
evidence=/run/evidence
prefix=/usr/lib/erhai/mesa
mkdir -p "$evidence"
exec >"$evidence/render-hardware.txt" 2>&1
echo TB_HARDWARE_RENDER_PROBE_BEGIN
date -u
cat /proc/uptime
dmesg >"$evidence/render-before-dmesg.txt"
env LD_LIBRARY_PATH="$prefix/lib" \
    LIBGL_DRIVERS_PATH="$prefix/lib/dri" \
    GBM_BACKENDS_PATH="$prefix/lib/gbm" \
    __EGL_VENDOR_LIBRARY_DIRS="$prefix/share/glvnd/egl_vendor.d" \
    timeout -k 5 45 python3 /usr/local/libexec/tb378fc-render-probe.py --hardware
result=$?
echo "PROBE_EXIT=$result"
dmesg >"$evidence/render-after-dmesg.txt"
cat /proc/uptime
echo TB_HARDWARE_RENDER_PROBE_END
exit "$result"
