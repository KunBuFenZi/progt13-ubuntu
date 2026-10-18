#!/usr/bin/env python3
"""Validate first PCM/real chip ID checks after a visible panel initialization."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
os.chdir(root)
def run(*args): subprocess.run([str(a) for a in args],check=True)
m=json.loads(Path('out/audio-late-identity-build.json').read_text())
runtime=Path('out/audio-display-late-runtime')
runtime.mkdir(exist_ok=False)
run('cp','-a','out/audio-runtime/.',runtime)
# Source the probe without starting a second diagnostic PID1 environment.
probe=Path('port/cpu-audio-probe-init').read_text()
assert probe.endswith('exec /bin/ram-base-init\n')
probe=probe.removesuffix('exec /bin/ram-base-init\n')+'wait\n'
(runtime/'bin/cpu-audio-probe-init').write_text(probe)
run('chmod','755',runtime/'bin/cpu-audio-probe-init')
manifest=json.loads((runtime/'manifest.json').read_text())
path=runtime/'bin/cpu-audio-probe-init'
manifest['files']['bin/cpu-audio-probe-init']={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mode':0o755}
(runtime/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for name in ['port/package-audio-display-late.py','port/audio-display-late-init','port/cpu-audio-probe-init','out/kms-reset.bin']:
 p=Path(name);m['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
Path('out/audio-display-late-package-build.json').write_text(json.dumps(m,indent=2)+'\n')
run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-audio-display-late',
    '--init-script','port/audio-display-late-init','--kms-test','out/kms-reset.bin',
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
    '--kernel','out/kernel-audio-late-identity/arch/arm64/boot/Image',
    '--dtb','out/abl-audio-gated/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-audio-gated/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb',
    '--ramdisk','out/initramfs-audio-display-late/initramfs.cpio.gz',
    '--build-manifest','out/audio-display-late-package-build.json',
    '--extra-cmdline',baseline['cmdline'][len(prefix)+1:],
    '--output','out/boot-audio-display-late','--image-name','boot-tb378fc-audio-display-late.img')
