#!/usr/bin/env python3
"""Discover the internal UFS in a RAM desktop with media writes blocked."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

directory = Path('/usr/share/tb378fc/ufs77')
manifest = json.loads((directory / 'manifest.json').read_text())
assert subprocess.check_output(['uname', '-r'], text=True).strip() == '7.2.0-tb378fc-wifi+'
dt = Path('/sys/firmware/devicetree/base')
assert b'lenovo,tb378fc-pmic-glink\0' in (dt / 'pmic-glink/compatible').read_bytes()
for path, phandle in manifest['external_phandles'].items():
    assert int.from_bytes((dt / path.lstrip('/') / 'phandle').read_bytes(), 'big') == phandle
for name, digest in manifest['files'].items():
    assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
for name in manifest['module_order']:
    if not Path('/sys/module/' + name.removesuffix('.ko').replace('-', '_')).exists():
        subprocess.run(['insmod', str(directory / name)], check=True, timeout=15)
if not Path('/sys/module/live_ufs_overlay77').exists():
    Path('/lib/firmware/tb378fc-ufs77.dtbo').write_bytes((directory / 'tb378fc-ufs77.dtbo').read_bytes())
    subprocess.run(['insmod', str(directory / 'live-ufs-overlay77.ko')], check=True, timeout=20)
for attempt in range(20):
    disks = sorted(Path('/sys/block').glob('sd*'))
    if len(disks) >= 6:
        break
    time.sleep(.5)
assert len(disks) >= 6, 'UFS discovery incomplete; inspect kernel log'
internal = [p for p in disks if '1d84000.ufs' in str(p.resolve())]
assert len(internal) == 6 and all((p / 'ro').read_text().strip() == '1' for p in internal)
record = {'status': 'UFS_READ_ONLY_DISCOVERED', 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'disks': [{'name':p.name, 'bytes':int((p/'size').read_text())*512, 'read_only':True} for p in internal]}
out = Path('/run/evidence/ufs77-startup.json')
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
