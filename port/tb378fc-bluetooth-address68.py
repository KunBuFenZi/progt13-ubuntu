#!/usr/bin/env python3
"""Set this unit's RAM BT address only while the controller is unconfigured."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

assert Path('/etc/tb378fc-candidate').read_text().strip()=='peripherals68'
serial=Path('/sys/devices/soc0/serial_number').read_bytes().strip()
assert serial and serial not in (b'0',b'00000000')
suffix=hashlib.sha256(b'TB378FC Linux RAM Bluetooth test v1\0'+serial).digest()[:5]
address='02:'+':'.join(f'{b:02X}' for b in suffix)
def management(*command,timeout=6):
    # BlueZ's shell frontend stalls on /dev/null's immediate HUP under systemd.
    # Hold a pipe writer open until the one-shot management command completes.
    readfd,writefd=os.pipe()
    try:
        return subprocess.run(['btmgmt','-i','0',*command],stdin=readfd,
                              capture_output=True,text=True,timeout=timeout)
    finally:
        os.close(readfd);os.close(writefd)
for attempt in range(20):
    result=management('config')
    if result.returncode==0 and 'missing options:' in result.stdout:
        break
    time.sleep(0.25)
else:
    raise RuntimeError('Native BT controller did not register')
missing=result.stdout.split('missing options:',1)[1].splitlines()[0].split()
changed=False
if missing:
    assert missing==['public-address'],missing
    result=management('public-addr',address,timeout=12)
    result.check_returncode()
    changed=True
# Setting the public address causes asynchronous controller setup. Wait for
# its completed info event; an immediate read can still contain the old value.
for attempt in range(40):
    result=management('info');result.check_returncode();info=result.stdout
    if re.search(r'\baddr '+re.escape(address)+r'\b',info,re.I):
        break
    time.sleep(0.25)
else:
    raise RuntimeError('Existing address differs; left unchanged')
record={'status':'RAM_LOCAL_UNIT_ADDRESS_READY','changed':changed,'address':address,
        'address_type':'Locally administered unicast, not the factory address',
        'derivation':'Hash of this unit SoC serial; raw serial is not logged',
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
output=Path('/run/evidence/peripherals68/bluetooth-address-service.json')
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
