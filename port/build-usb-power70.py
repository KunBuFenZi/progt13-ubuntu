#!/usr/bin/env python3
"""Build the native USB current path separately, restoring the baseline source."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
kernel = root / 'kernel'
base = root / 'out/kernel-usbc70'
work = root / 'out/kernel-usbc70b'
source = kernel / 'drivers/power/supply/qcom_battmgr.c'
candidate = root / 'out/native-usb-power70/qcom_battmgr.c'
proof = json.loads(candidate.with_name('manifest.json').read_text())
original = source.read_bytes()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(source) == proof['base_source_sha256']
assert sha(candidate) == proof['candidate_source_sha256']
assert not work.exists()
subprocess.run(['cp', '-a', '--reflink=auto', str(base), str(work)], check=True)
try:
    source.write_bytes(candidate.read_bytes())
    subprocess.run(['make', '-C', str(kernel), 'O=' + str(work), 'LOCALVERSION=+', '-j2', 'Image'],
                   check=True, env=dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-'))
finally:
    source.write_bytes(original)
assert source.read_bytes() == original
record = json.loads((base / 'manifest.json').read_text())
record.update(status='OFFLINE_USB_C_AND_NATIVE_CHARGER_KERNEL_BUILT_NOT_BOOTED',
              image_sha256=sha(work / 'arch/arm64/boot/Image'), native_usb_power=proof,
              baseline_source_restored=True)
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(record['status'], record['image_sha256'])
