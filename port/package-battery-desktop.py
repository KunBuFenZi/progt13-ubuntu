#!/usr/bin/env python3
"""Integrate the native battery probe into a separate, RAM-only desktop trial."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--release-battery-ui', action='store_true')
p.add_argument('--corrected-power', action='store_true')
p.add_argument('--corrected-current', action='store_true')
args = p.parse_args()
if args.corrected_current:
    args.corrected_power = True
version = ('v8' if args.release_battery_ui else 'v8-held') if args.corrected_current else (('v71' if args.release_battery_ui else 'v7') if args.corrected_power else ('v61' if args.release_battery_ui else 'v6'))
probe = 'out/battery-probe-v3' if args.corrected_current else ('out/battery-probe-v2' if args.corrected_power else 'out/battery-probe')
manifest = json.loads(Path(probe+'/build.json').read_text())
manifest['status'] = 'BATTERY_DESKTOP_CANDIDATE_NOT_COLD_BOOTED'
for name in ['port/package-battery-desktop.py', 'port/prepare-desktop-settings.py',
             'port/wifi-passive-discovery.py', 'port/setup-wifi-identity.py']:
    path = Path(name)
    manifest['files'][name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                              'size': path.stat().st_size}
build = Path('out/battery-desktop-' + version + '-build.json')
build.write_text(json.dumps(manifest, indent=2)+'\n')
subprocess.run([sys.executable, 'port/package-wireless-desktop.py',
    '--output', 'out/boot-battery-desktop-' + version,
    '--image-name', 'boot-tb378fc-battery-desktop-' + version + '.img',
    '--initramfs-output', 'out/initramfs-battery-desktop-' + version,
    '--kernel', 'out/kernel-battery-v2/arch/arm64/boot/Image' if args.corrected_current else ('out/kernel-battery/arch/arm64/boot/Image' if args.corrected_power else 'out/kernel-adsp/arch/arm64/boot/Image'),
    '--build-manifest', str(build), '--zram',
    '--usb-ssh-runtime', 'out/usb-ssh-runtime.tar',
    '--usb-ssh-public-key', 'out/device-ssh/id_ed25519.pub',
    '--adsp-firmware-dir', 'diagnostics/firmware/adsp',
    '--dtb', probe+'/abl/erhai-abl.dtb',
    '--mainline-dtb', probe+'/sm8750-lenovo-tb378fc-battery.dtb',
    *([] if args.release_battery_ui else ['--hold-battery-ui'])], check=True)
