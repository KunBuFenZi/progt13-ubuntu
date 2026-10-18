#!/usr/bin/env python3
"""Package a short RAM-only native ADSP discovery trial, without desktop layers."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
def run(*args):subprocess.run([str(a) for a in args],check=True)
run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-adsp-probe',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu','--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp')
baseline=json.loads(Path('out/boot-unattended-v5/manifest.json').read_text())
base='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert baseline['cmdline'].startswith(base+' ')
extra=baseline['cmdline'][len(base)+1:].replace(' systemd.unit=graphical.target','')
run(sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-adsp/arch/arm64/boot/Image',
    '--dtb','out/abl-adsp/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-adsp/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-adsp.dtb',
    '--ramdisk','out/initramfs-adsp-probe/initramfs.cpio.gz',
    '--build-manifest','out/adsp-build.json','--extra-cmdline',extra,
    '--output','out/boot-adsp-probe','--image-name','boot-tb378fc-adsp-probe-v2.img')
