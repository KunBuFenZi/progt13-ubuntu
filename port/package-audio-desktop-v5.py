#!/usr/bin/env python3
"""Cold-boot desktop candidate using attempt 47's CPU/audio kernel."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)
m = json.loads(Path('out/cpu-audio-ready-build.json').read_text())
assert Path('kernel/sound/soc/codecs/aw88480.c').read_bytes() == Path('port/aw88480.c').read_bytes()
assert hashlib.sha256(Path('port/aw88480.c').read_bytes()).hexdigest() == m['files']['port/aw88480.c']['sha256']
m['status'] = 'EIGHT_CPU_AUDIO_DESKTOP_CANDIDATE_NOT_COLD_BOOTED'
for name in ['port/audio/HiFi.conf','port/audio/Lenovo-TB378FC.conf',
             'port/prepare-audio-desktop.py','port/prepare-desktop-settings.py',
             'port/package-wireless-desktop.py','port/desktop-init',
             'port/package-audio-desktop-v5.py']:
    p = Path(name)
    m['files'][name] = {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
build = Path('out/audio-desktop-v5-build.json')
build.write_text(json.dumps(m,indent=2)+'\n')
subprocess.run([sys.executable,'port/package-wireless-desktop.py',
    '--output','out/boot-audio-desktop-v5',
    '--image-name','boot-tb378fc-audio-desktop-v5.img',
    '--initramfs-output','out/initramfs-audio-desktop-v5',
    '--kernel','out/kernel-cpu-audio-ready/arch/arm64/boot/Image',
    '--build-manifest',str(build),'--zram','--nr-cpus','8',
    '--usb-ssh-runtime','out/usb-ssh-runtime.tar',
    '--usb-ssh-public-key','out/device-ssh/id_ed25519.pub',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf',
    '--audio-topology','out/topology-tb378fc/Lenovo-TB378FC-tplg.bin',
    '--dtb','out/abl-audio-gated/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-audio-gated/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb'],check=True)
