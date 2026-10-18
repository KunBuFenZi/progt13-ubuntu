#!/usr/bin/env python3
"""Compare amp GPIO initialization without issuing any I2C chip ID read."""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
os.chdir(root)
m=json.loads(Path('out/audio-gpio-only-build.json').read_text())
dtb='out/display-sound-disabled-tree/sm8750-lenovo-tb378fc-audio.dtb'
source=json.loads(Path('out/display-sound-disabled-build.json').read_text())
m['files'][dtb]=source['files'][dtb]
Path('out/audio-gpio-only-package-build.json').write_text(json.dumps(m,indent=2)+'\n')
baseline=json.loads(Path('out/boot-display-sound-disabled/manifest.json').read_text())
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert baseline['cmdline'].startswith(prefix+' ')
subprocess.run([sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-audio-gpio-only/arch/arm64/boot/Image',
    '--dtb','out/display-sound-disabled-tree/abl/erhai-abl.dtb',
    '--mainline-dtb',dtb,
    '--ramdisk','out/initramfs-display-sound-disabled/initramfs.cpio.gz',
    '--build-manifest','out/audio-gpio-only-package-build.json',
    '--extra-cmdline',baseline['cmdline'][len(prefix)+1:]+' snd_soc_aw88480.skip_probe_read=1',
    '--output','out/boot-audio-gpio-only','--image-name','boot-tb378fc-audio-gpio-only.img'],check=True)
