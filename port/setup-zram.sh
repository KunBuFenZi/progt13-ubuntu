#!/bin/sh
# RAM-only swap: never attach a backing block device.
set -eu
test -f /etc/tb378fc-build-id
test -e /sys/block/zram0/disksize
test "$(cat /sys/block/zram0/disksize)" = 0
echo lz4 > /sys/block/zram0/comp_algorithm
echo 1073741824 > /sys/block/zram0/mem_limit
echo 2147483648 > /sys/block/zram0/disksize
mkswap /dev/zram0
swapon -p 100 /dev/zram0
echo 100 > /proc/sys/vm/swappiness
echo 0 > /proc/sys/vm/page-cluster
echo madvise > /sys/kernel/mm/transparent_hugepage/enabled
cat /proc/swaps
