#!/usr/bin/env python3
"""Probe CPUCP/SCMI and online CPUs only after USB diagnostics are running."""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
os.chdir(root)
def run(*args): subprocess.run([str(a) for a in args],check=True)
run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-cpufreq',
    '--init-script','port/cpu-probe-init',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu','--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf',
    '--audio-runtime-dir','out/audio-runtime',
    '--audio-topology','out/topology-tb378fc/Lenovo-TB378FC-tplg.bin')
m=json.loads(Path('out/boot-audio-ready/manifest.json').read_text())
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert m['cmdline'].startswith(prefix+' ') and m['cmdline'].count('nr_cpus=7')==1
run(sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-cpufreq/arch/arm64/boot/Image',
    '--dtb','out/abl-audio-gated/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-audio-gated/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb',
    '--ramdisk','out/initramfs-cpufreq/initramfs.cpio.gz',
    '--build-manifest','out/cpufreq-build.json',
    '--extra-cmdline',m['cmdline'][len(prefix)+1:].replace('nr_cpus=7','nr_cpus=8'),
    '--output','out/boot-cpufreq','--image-name','boot-tb378fc-cpufreq.img')
