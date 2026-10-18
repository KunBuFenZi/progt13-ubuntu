#!/usr/bin/env python3
"""Package a short RAM AudioReach discovery session; no speaker codec enabled."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)
old = json.loads(Path('out/battery-probe-v3/boot/manifest.json').read_text())
prefix = ('rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 '
          'log_buf_len=2M printk.time=1 tb378fc.stage=1')
assert old['cmdline'].startswith(prefix+' ')
manifest = json.loads(Path('out/audio-foundation-build.json').read_text())
base = json.loads(Path('out/battery-probe-v3/build.json').read_text())
dtb = 'out/battery-probe-v3/sm8750-lenovo-tb378fc-battery.dtb'
assert hashlib.sha256(Path(dtb).read_bytes()).hexdigest() == base['files'][dtb]['sha256']
manifest['files'][dtb] = base['files'][dtb]
Path('out/audio-foundation-package-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
subprocess.run([sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-audio-foundation/arch/arm64/boot/Image',
    '--dtb','out/battery-probe-v3/abl/erhai-abl.dtb',
    '--mainline-dtb','out/battery-probe-v3/sm8750-lenovo-tb378fc-battery.dtb',
    '--ramdisk','out/initramfs-adsp-probe/initramfs.cpio.gz',
    '--build-manifest','out/audio-foundation-package-build.json',
    '--extra-cmdline',old['cmdline'][len(prefix)+1:],
    '--output','out/boot-audio-foundation','--image-name','boot-tb378fc-audio-foundation-v2.img'],check=True)
