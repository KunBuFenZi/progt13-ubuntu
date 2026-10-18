#!/system/bin/sh
MODDIR=${0%/*}
export TB378FC_SWITCH_CONFIG="$MODDIR/device.conf"
exec /data/adb/ksu/bin/busybox sh "$MODDIR/tb378fc-switch" to-ubuntu
