#!/usr/bin/env python3
"""Key-only RAM SSH on the user's authorized WLAN, reusing the pinned USB host key."""
import ipaddress
import json
import os
from pathlib import Path
import subprocess

def output(*args):
    return subprocess.check_output(args, text=True, timeout=10).strip()

assert Path('/etc/tb378fc-build-id').is_file()
config_root = Path('/run/tb378fc-ssh')
assert (config_root / 'host_key').is_file() and (config_root / 'authorized_keys').is_file()
connection = output('nmcli', '-g', 'GENERAL.CONNECTION', 'device', 'show', 'wlp1s0')
ssid = output('nmcli', '-g', '802-11-wireless.ssid', 'connection', 'show', connection)
assert ssid in ['TEST_WIFI', 'TEST_WIFI_5'], 'Authorized WLAN required'
addresses = json.loads(output('ip', '-j', '-4', 'address', 'show', 'dev', 'wlp1s0'))
ips = [a['local'] for device in addresses for a in device['addr_info']
       if a['scope'] == 'global' and ipaddress.ip_address(a['local']) in ipaddress.ip_network('192.168.68.0/24')]
assert len(ips) == 1, ips
config = config_root / 'sshd-wifi70.conf'
config.write_text(f'''Port 2222
ListenAddress {ips[0]}
HostKey /run/tb378fc-ssh/host_key
PidFile /run/tb378fc-ssh/sshd-wifi70.pid
AuthorizedKeysFile /run/tb378fc-ssh/authorized_keys
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM yes
AllowUsers root
Subsystem sftp /usr/lib/openssh/sftp-server
''')
config.chmod(0o600)
subprocess.run(['/usr/sbin/sshd', '-t', '-f', str(config)], check=True, timeout=10)
print(json.dumps({'wifi_ssh': ips[0], 'port': 2222, 'same_usb_host_key': True}), flush=True)
os.execv('/usr/sbin/sshd', ['/usr/sbin/sshd', '-D', '-e', '-f', str(config)])
