#!/usr/bin/env python3
"""Isolate CPU online/governor effects on native panel initialization."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
os.chdir(root)
def run(*args): subprocess.run([str(a) for a in args],check=True)
m=json.loads(Path('out/cpu-audio-ready-build.json').read_text())
m['status']='CPU_DISPLAY_GOVERNOR_ISOLATION_NOT_TESTED'
for name in ['port/cpu-display-probe-init','port/package-cpu-display-probe.py','port/kms-test.c','out/kms-test']:
    p=Path(name)
    m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/cpu-display-probe-build.json').write_text(json.dumps(m,indent=2)+'\n')
run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-cpu-display-probe',
    '--init-script','port/cpu-display-probe-init','--kms-test','out/kms-test',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu','--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf',
    '--audio-runtime-dir','out/audio-runtime',
    '--audio-topology','out/topology-tb378fc/Lenovo-TB378FC-tplg.bin')
baseline=json.loads(Path('out/boot-cpu-audio-ready/manifest.json').read_text())
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert baseline['cmdline'].startswith(prefix+' ')
run(sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-cpu-audio-ready/arch/arm64/boot/Image',
    '--dtb','out/abl-audio-gated/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-audio-gated/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb',
    '--ramdisk','out/initramfs-cpu-display-probe/initramfs.cpio.gz',
    '--build-manifest','out/cpu-display-probe-build.json',
    '--extra-cmdline',baseline['cmdline'][len(prefix)+1:],
    '--output','out/boot-cpu-display-probe','--image-name','boot-tb378fc-cpu-display-probe.img')
