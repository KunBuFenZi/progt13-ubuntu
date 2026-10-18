#!/bin/sh
# Disposable, key-only diagnostic SSH bound to the USB network address.
set -eu
test -f /etc/tb378fc-build-id
mkdir -p /run/evidence /run/tb378fc-ssh /run/sshd
chmod 755 /run
chmod 700 /run/tb378fc-ssh
exec > /run/evidence/ssh-setup.txt 2>&1
if [ -f /etc/tb378fc-usb-ssh.pub ]; then
    cp /etc/tb378fc-usb-ssh.pub /run/tb378fc-ssh/authorized_keys
    chmod 600 /run/tb378fc-ssh/authorized_keys
fi
test -s /run/tb378fc-ssh/authorized_keys
systemctl mask ssh.service ssh.socket
if [ ! -x /usr/sbin/sshd ]; then
    export DEBIAN_FRONTEND=noninteractive
    if [ -f /etc/apt/sources.list.d/cdrom.sources ]; then
        if grep -q 'file:///cdrom' /etc/apt/sources.list.d/cdrom.sources; then
            sed -i '/^Enabled:/d; 1i Enabled: no' /etc/apt/sources.list.d/cdrom.sources
        fi
    fi
    apt-get update
    apt-get install -y --no-install-recommends openssh-server
fi
if [ ! -f /run/tb378fc-ssh/host_key ]; then
    ssh-keygen -q -t ed25519 -N '' -f /run/tb378fc-ssh/host_key
fi
cat > /run/tb378fc-ssh/sshd_config <<'EOF'
Port 2222
ListenAddress 192.168.77.2
HostKey /run/tb378fc-ssh/host_key
PidFile /run/tb378fc-ssh/sshd.pid
AuthorizedKeysFile /run/tb378fc-ssh/authorized_keys
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM yes
AllowUsers root
Subsystem sftp /usr/lib/openssh/sftp-server
EOF
/usr/sbin/sshd -t -f /run/tb378fc-ssh/sshd_config
systemd-run --unit=tb378fc-usb-ssh /usr/sbin/sshd -D -e -f /run/tb378fc-ssh/sshd_config
cp /run/tb378fc-ssh/host_key.pub /run/evidence/ssh-hostkey.pub
echo USB_SSH_READY
