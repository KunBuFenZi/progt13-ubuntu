#!/usr/bin/env python3
"""Package a short RAM enumeration test for all four native AW88480 codecs."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)

def run(*args):
    subprocess.run([str(x) for x in args],check=True)

run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-aw88480',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu',
    '--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf')
old = json.loads(Path('out/boot-audio-foundation/manifest.json').read_text())
prefix = ('rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 '
          'log_buf_len=2M printk.time=1 tb378fc.stage=1')
assert old['cmdline'].startswith(prefix+' ')
run(sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-aw88480/arch/arm64/boot/Image',
    '--dtb','out/abl-aw88480/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-aw88480/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio-probe.dtb',
    '--ramdisk','out/initramfs-aw88480/initramfs.cpio.gz',
    '--build-manifest','out/aw88480-build.json',
    '--extra-cmdline',old['cmdline'][len(prefix)+1:],
    '--output','out/boot-aw88480','--image-name','boot-tb378fc-aw88480-probe-v2.img')
