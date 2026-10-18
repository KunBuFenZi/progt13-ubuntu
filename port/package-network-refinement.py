#!/usr/bin/env python3
"""Package the scan-cache correction with the frozen, verified desktop kernel."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
checkpoint=Path('out/checkpoint-unattended-v5-build')
proof=json.loads((checkpoint/'checkpoint.json').read_text())
for name in ('Image','config'):
    assert hashlib.sha256((checkpoint/name).read_bytes()).hexdigest()==proof['files'][name]
manifest=json.loads(Path('out/keys-build.json').read_text())
manifest['status']='NETWORK_CACHE_REFINEMENT_WITH_FROZEN_DESKTOP_KERNEL_NOT_COLD_BOOTED'
for name in ['out/checkpoint-unattended-v5-build/Image','out/checkpoint-unattended-v5-build/config',
             'port/wifi-passive-discovery.py','port/setup-wifi-identity.py',
             'port/prepare-desktop-settings.py','port/package-network-refinement.py']:
    p=Path(name);manifest['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
path=Path('out/network-refinement-build.json');path.write_text(json.dumps(manifest,indent=2)+'\n')
subprocess.run([sys.executable,'port/package-wireless-desktop.py',
    '--output','out/boot-unattended-v51','--image-name','boot-tb378fc-unattended-v51.img',
    '--initramfs-output','out/initramfs-unattended-v51',
    '--kernel',str(checkpoint/'Image'),'--build-manifest',str(path),'--zram',
    '--usb-ssh-runtime','out/usb-ssh-runtime.tar','--usb-ssh-public-key','out/device-ssh/id_ed25519.pub'],check=True)
