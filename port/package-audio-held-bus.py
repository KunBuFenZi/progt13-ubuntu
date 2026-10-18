#!/usr/bin/env python3
"""Diagnostic: keep I2C power before amp probing, test panel and zero PCM."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
os.chdir(root)
def run(*args): subprocess.run([str(a) for a in args],check=True)
m=json.loads(Path('out/audio-held-bus-build.json').read_text())
runtime=Path('out/audio-held-bus-runtime')
runtime.mkdir(exist_ok=False)
run('cp','-a','out/audio-runtime/.',runtime)
run('cp','port/cpu-audio-probe-init',runtime/'bin/cpu-audio-probe-init')
run('chmod','755',runtime/'bin/cpu-audio-probe-init')
run('aarch64-linux-gnu-gcc','-static','-O2','-Wall','-Wextra','-Werror',
    '-I','out/display-uapi/include','port/kms-test.c','-o',runtime/'bin/kms-test')
runtime_manifest=json.loads((runtime/'manifest.json').read_text())
for name in ['bin/cpu-audio-probe-init','bin/kms-test']:
    path=runtime/name
    runtime_manifest['files'][name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mode':0o755}
(runtime/'manifest.json').write_text(json.dumps(runtime_manifest,indent=2)+'\n')
for name in ['port/audio-held-bus-init','port/package-audio-held-bus.py','port/cpu-audio-probe-init','port/kms-test.c']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/audio-held-bus-package-build.json').write_text(json.dumps(m,indent=2)+'\n')
run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-audio-held-bus',
    '--init-script','port/audio-held-bus-init',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu','--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf',
    '--audio-runtime-dir',runtime,
    '--audio-topology','out/topology-tb378fc/Lenovo-TB378FC-tplg.bin')
baseline=json.loads(Path('out/boot-cpu-audio-ready/manifest.json').read_text())
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert baseline['cmdline'].startswith(prefix+' ')
run(sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-audio-held-bus/arch/arm64/boot/Image',
    '--dtb','out/abl-audio-gated/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-audio-gated/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb',
    '--ramdisk','out/initramfs-audio-held-bus/initramfs.cpio.gz',
    '--build-manifest','out/audio-held-bus-package-build.json',
    '--extra-cmdline',baseline['cmdline'][len(prefix)+1:]+' snd_soc_aw88480.hold_bus_awake=1',
    '--output','out/boot-audio-held-bus','--image-name','boot-tb378fc-audio-held-bus.img')
