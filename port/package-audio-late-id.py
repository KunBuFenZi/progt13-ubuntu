#!/usr/bin/env python3
"""Isolate the first amp read after panel initialization; no PCM playback."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
os.chdir(root)
def run(*args): subprocess.run([str(a) for a in args],check=True)
m=json.loads(Path('out/audio-late-id-build.json').read_text())
dtb='out/display-sound-disabled-tree/sm8750-lenovo-tb378fc-audio.dtb'
source=json.loads(Path('out/display-sound-disabled-build.json').read_text())
m['files'][dtb]=source['files'][dtb]
for name in ['port/package-audio-late-id.py','port/audio-late-id-init','port/kms-test.c','out/kms-reset.bin']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/audio-late-id-package-build.json').write_text(json.dumps(m,indent=2)+'\n')
run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-audio-late-id',
    '--init-script','port/audio-late-id-init','--kms-test','out/kms-reset.bin',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu','--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf',
    '--audio-runtime-dir','out/audio-runtime',
    '--audio-topology','out/topology-tb378fc/Lenovo-TB378FC-tplg.bin')
baseline=json.loads(Path('out/boot-audio-gpio-only/manifest.json').read_text())
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert baseline['cmdline'].startswith(prefix+' ')
run(sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-audio-late-id/arch/arm64/boot/Image',
    '--dtb','out/display-sound-disabled-tree/abl/erhai-abl.dtb','--mainline-dtb',dtb,
    '--ramdisk','out/initramfs-audio-late-id/initramfs.cpio.gz',
    '--build-manifest','out/audio-late-id-package-build.json',
    '--extra-cmdline',baseline['cmdline'][len(prefix)+1:],
    '--output','out/boot-audio-late-id','--image-name','boot-tb378fc-audio-late-id.img')
