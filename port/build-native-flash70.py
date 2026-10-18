#!/usr/bin/env python3
"""Compile native flash DT and stock modules offline against the accepted kernel.

No boot image is built, selected or sent to the tablet.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
work = root / 'out/native-flash70'
work.mkdir(exist_ok=False)
sdk = root / 'out/kernel-peripherals68'
kernel = root / 'kernel'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
native_id = root / 'diagnostics/native-peripherals70/flash-id.txt'
observed = dict(line.split(':', 1) for line in native_id.read_text().splitlines() if ':' in line)
assert int(observed['ee04'], 16) == 0x18
assert int(observed['ee05'], 16) == 0x07
assert int(observed['ee00'], 16) == 0x01

source = root / 'port/tb378fc-flash70.dtso'
overlay = work / 'tb378fc-flash70.dtbo'
subprocess.run(['dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', str(overlay), str(source)], check=True)
baseline = root / 'out/peripherals-tree68/sm8750-lenovo-tb378fc-peripherals.dtb'
merged = work / 'offline-merged-only.dtb'
target = '/soc@0/spmi@c400000/pmic@1/led-controller@ee00'

def get(path, prop, kind='s', tree=baseline):
    return subprocess.check_output(['fdtget', '-t', kind, str(tree), path, prop], text=True).strip()

assert get(target, 'status') == 'disabled'
assert get(target, 'compatible').split() == ['qcom,pm8550-flash-led', 'qcom,spmi-flash-led']
assert get(target, 'reg', 'x') == 'ee00'
subprocess.run(['fdtoverlay', '-i', str(baseline), '-o', str(merged), str(overlay)], check=True)
assert get(target, 'status', tree=merged) == 'okay'
assert get(target + '/led-0', 'led-sources', 'i', merged) == '1 4'
assert get(target + '/led-0', 'led-max-microamp', 'i', merged) == '100000'

for name, original in [('led-class-flash', kernel / 'drivers/leds/led-class-flash.c'),
                       ('leds-qcom-flash', kernel / 'drivers/leds/flash/leds-qcom-flash.c')]:
    shutil.copy2(original, work / (name + '.c'))
(work / 'Makefile').write_text('obj-m += led-class-flash.o leds-qcom-flash.o\n')
(sdk / 'Module.symvers').write_bytes((sdk / 'vmlinux.symvers').read_bytes())
subprocess.run(['make', '-C', str(kernel), 'O=' + str(sdk), 'LOCALVERSION=+', '-j2',
                'M=' + str(work), 'modules'], check=True,
               env=dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-'))
exports = {line.split()[1] for table in [sdk / 'vmlinux.symvers', work / 'Module.symvers']
           for line in table.read_text().splitlines()}
modules = {}
for name in ['led-class-flash.ko', 'leds-qcom-flash.ko']:
    module = work / name
    imports = {line.split()[-1] for line in subprocess.check_output(
        ['aarch64-linux-gnu-nm', '-u', str(module)], text=True).splitlines()}
    assert not imports - exports, imports - exports
    modules[name] = {'sha256': sha(module), 'bytes': module.stat().st_size}
record = {'status': 'OFFLINE_COMPILED_AND_OVERLAY_MERGED_NOT_LOADED_OR_LIGHT_TESTED',
          'native_flash_id': {'revision': 1, 'type': 0x18, 'subtype': 7},
          'native_id_sha256': sha(native_id), 'source_sha256': sha(source),
          'overlay_sha256': sha(overlay), 'baseline_dtb_sha256': sha(baseline),
          'kernel_config_sha256': sha(sdk / '.config'), 'modules': modules,
          'channels_one_based': [1, 4], 'channels_vendor_zero_based': [0, 3],
          'trial_torch_total_microamp': 100000, 'trial_flash_total_microamp': 200000,
          'trial_timeout_microseconds': 200000,
          'remaining': ['RAM-only overlay application', 'Default-off check',
                        'Brief low-current torch verification', 'Timeout/off/fault verification'],
          'scope': 'Only offline artifacts. No flash, storage mount, reboot or live LED activation.'}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
