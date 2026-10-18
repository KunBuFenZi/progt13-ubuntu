#!/usr/bin/env python3
"""Build an isolated USB-C kernel; keep the accepted 120 Hz panel and kernel68."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
kernel = root / 'kernel'
base = root / 'out/kernel-peripherals68'
work = root / 'out/kernel-usbc70'
assert not work.exists()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
baseline_hash = sha(base / 'arch/arm64/boot/Image')
subprocess.run(['cp', '-a', '--reflink=auto', str(base), str(work)], check=True)
enable = ['USB', 'USB_XHCI_HCD', 'USB_XHCI_PLATFORM', 'USB_ROLE_SWITCH',
          'TYPEC_UCSI', 'UCSI_PMIC_GLINK', 'TYPEC_MUX_WCD939X_USBSS',
          'TYPEC_DP_ALTMODE', 'HID', 'HID_GENERIC', 'USB_HID', 'INPUT_EVDEV',
          'DRM_MSM_DP', 'PHY_QCOM_QMP_COMBO']
for option in enable:
    subprocess.run([str(kernel / 'scripts/config'), '--file', str(work / '.config'),
                    '-e', option], check=True)
env = dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-')
subprocess.run(['make', '-C', str(kernel), 'O=' + str(work), 'LOCALVERSION=+', 'olddefconfig'],
               check=True, env=env)
config = (work / '.config').read_text()
for option in enable:
    assert 'CONFIG_' + option + '=y\n' in config, option
before = set((base / '.config').read_text().splitlines())
after = set(config.splitlines())
record = {'status': 'BUILDING_USB_C_CANDIDATE_NO_DEVICE_CHANGES',
          'base_image_sha256': baseline_hash, 'base_config_sha256': sha(base / '.config'),
          'config_sha256': sha(work / '.config'), 'config_added': sorted(after - before),
          'config_removed': sorted(before - after),
          'scope': 'Enable native UCSI, WCD939x SBU mux, DP alt mode, USB host HID; panel source and preferred120 unchanged',
          'panel_source_sha256': sha(kernel / 'drivers/gpu/drm/panel/panel-novatek-nt36526.c')}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
subprocess.run(['make', '-C', str(kernel), 'O=' + str(work), 'LOCALVERSION=+', '-j2', 'Image'],
               check=True, env=env)
assert sha(base / 'arch/arm64/boot/Image') == baseline_hash
record.update(status='OFFLINE_KERNEL_BUILT_NOT_BOOTED', image_sha256=sha(work / 'arch/arm64/boot/Image'))
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2), flush=True)
