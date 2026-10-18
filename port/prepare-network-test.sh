#!/bin/sh
# Enable Wi-Fi in the RAM desktop while leaving the USB diagnostic NIC alone.
set -eu
test -f /etc/tb378fc-build-id
mkdir -p /run/evidence /etc/NetworkManager/conf.d
exec > /run/evidence/wifi-manager.txt 2>&1
printf '[keyfile]\nunmanaged-devices=interface-name:usb0\n' > /etc/NetworkManager/conf.d/90-tb378fc-usb.conf
iface=
for path in /sys/class/net/*; do
    if [ -d "$path/wireless" ]; then
        test -z "$iface"
        iface=${path##*/}
    fi
done
test -n "$iface"
printf '%s\n' "$iface" > /run/evidence/wifi-interface.txt
address=$(cat "/sys/class/net/$iface/address")
# The vendor firmware exposes a common placeholder without its Android MAC
# provider. Use a fresh local address for this RAM trial, before association.
if [ "$address" = '00:03:7f:12:34:56' ]; then
    local_address=$(python3 -c 'import secrets; print("02:"+":".join(f"{x:02x}" for x in secrets.token_bytes(5)))')
    ip link set dev "$iface" down
    ip link set dev "$iface" address "$local_address"
    echo LOCAL_TRIAL_MAC_ASSIGNED
fi
systemctl unmask NetworkManager.service NetworkManager-wait-online.service
systemctl start NetworkManager.service
nmcli radio wifi on
nmcli general status
nmcli device status
nmcli --wait 25 -f SSID,SIGNAL,SECURITY,FREQ device wifi list ifname "$iface" --rescan yes > /run/evidence/wifi-scan.txt
echo WIFI_MANAGER_READY
