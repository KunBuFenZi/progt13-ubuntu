#!/usr/bin/env python3
"""Integrate the tested native audio graph in the RAM desktop."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)
m = json.loads(Path('out/audio-ready-build.json').read_text())
# Earlier manifests also carry the first probe's installed-codec record.
# The compiled driver's own source was refreshed in the ready build. Require
# byte identity before replacing that inherited entry with the recorded hash.
assert Path('kernel/sound/soc/codecs/aw88480.c').read_bytes() == Path('port/aw88480.c').read_bytes()
assert hashlib.sha256(Path('port/aw88480.c').read_bytes()).hexdigest() == m['files']['port/aw88480.c']['sha256']
m['files']['kernel/sound/soc/codecs/aw88480.c'] = dict(m['files']['port/aw88480.c'])
m['status'] = 'AUDIO_DESKTOP_CANDIDATE_NOT_COLD_BOOTED'
for name in ['port/prepare-audio-desktop.py','port/prepare-desktop-settings.py',
             'port/package-wireless-desktop.py','port/package-audio-desktop.py']:
    p = Path(name)
    m['files'][name] = {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
build = Path('out/audio-desktop-build.json')
build.write_text(json.dumps(m,indent=2)+'\n')
subprocess.run([sys.executable,'port/package-wireless-desktop.py',
    '--output','out/boot-audio-desktop-v1',
    '--image-name','boot-tb378fc-audio-desktop-v1.img',
    '--initramfs-output','out/initramfs-audio-desktop-v1',
    '--kernel','out/kernel-audio-ready/arch/arm64/boot/Image',
    '--build-manifest',str(build),'--zram',
    '--usb-ssh-runtime','out/usb-ssh-runtime.tar',
    '--usb-ssh-public-key','out/device-ssh/id_ed25519.pub',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf',
    '--audio-topology','out/topology-tb378fc/Lenovo-TB378FC-tplg.bin',
    '--dtb','out/abl-audio-ready/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-audio-ready/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb'],check=True)
