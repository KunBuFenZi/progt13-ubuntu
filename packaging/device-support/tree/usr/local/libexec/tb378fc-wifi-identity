#!/usr/bin/env python3
"""Replace this firmware's shared placeholder before NetworkManager starts."""
from pathlib import Path
import secrets
import subprocess
import time

assert Path('/etc/tb378fc-build-id').is_file()
for _ in range(20):
    interfaces=[p for p in Path('/sys/class/net').iterdir() if (p/'wireless').is_dir()]
    if interfaces:break
    time.sleep(.25)
assert len(interfaces)==1,'Expected the single native WLAN interface'
device=interfaces[0]
assert (device/'device/vendor').read_text().strip()=='0x17cb'
assert (device/'device/device').read_text().strip()=='0x110e'
if (device/'address').read_text().strip()=='00:03:7f:12:34:56':
    address='02:'+':'.join(f'{x:02x}' for x in secrets.token_bytes(5))
    subprocess.run(['ip','link','set',device.name,'down'],check=True)
    subprocess.run(['ip','link','set',device.name,'address',address],check=True)
    subprocess.run(['ip','link','set',device.name,'up'],check=True)
    print('LOCAL_RAM_WLAN_ADDRESS_ASSIGNED')
else:
    print('EXISTING_UNIQUE_WLAN_ADDRESS_PRESERVED')
