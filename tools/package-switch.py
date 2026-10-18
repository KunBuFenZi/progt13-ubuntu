#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Package the same-slot switcher for one owner's tablet; no device I/O."""
import argparse
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--serial', required=True, help='Physical ADB/fastboot serial, not ro.product.model')
p.add_argument('--soc-serial', required=True, help='Linux /sys/devices/soc0/serial_number')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
if not re.fullmatch(r'[A-Za-z0-9_-]{4,64}', a.serial) or not re.fullmatch(r'[0-9]{1,20}', a.soc_serial):
    p.error('Invalid device identity')
if 'NOT_CONFIGURED' in a.serial:
    p.error('Use the physical identity of your own device')
if a.output.exists():
    p.error('Output already exists')
a.output.parent.mkdir(parents=True, exist_ok=True)
config = f'TB378FC_SERIAL={a.serial}\nTB378FC_SOC_SERIAL={a.soc_serial}\n'
with zipfile.ZipFile(a.output, 'x', compression=zipfile.ZIP_DEFLATED) as z:
    for name in ['module.prop', 'action.sh', 'customize.sh']:
        z.write(ROOT / 'switch/ksu-module' / name, name)
    z.write(ROOT / 'switch/tb378fc-switch', 'tb378fc-switch')
    z.writestr('device.conf', config)
# Same identity file is installed into Ubuntu; never put it in Git.
a.output.with_suffix('.device.conf').write_text(config)
print(a.output)
