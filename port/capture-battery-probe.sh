#!/bin/sh
# Read-only observations. Do not write charge controls or start desktop policy.
echo BATTERY_PROBE_BEGIN
cat /proc/uptime /etc/build-id
for n in /sys/class/remoteproc/remoteproc*; do
    [ -f "$n/name" ] || continue
    echo "$n"
    cat "$n/name" "$n/state" "$n/firmware"
done
echo RPMSG_CHANNELS
ls -l /sys/bus/rpmsg/devices
for n in /sys/bus/rpmsg/devices/*/name; do
    [ ! -f "$n" ] || cat "$n"
done
echo POWER_SUPPLY
for n in /sys/class/power_supply/*; do
    [ -d "$n" ] || continue
    echo "$n"
    for p in type present status health capacity voltage_now current_now temp charge_now charge_full charge_full_design online usb_type; do
        [ -f "$n/$p" ] || continue
        echo "$p:"
        /bin/busybox timeout 3 cat "$n/$p"
    done
done
echo KERNEL_LOG
dmesg
echo BATTERY_PROBE_END
