#!/usr/bin/env python3
"""Package native four-speaker playback diagnostics; no automatic sound."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)
def run(*args):
    subprocess.run([str(x) for x in args],check=True)

# Put the small test scripts in the hash-verified runtime manifest.
runtime = Path('out/audio-runtime')
m = json.loads((runtime/'manifest.json').read_text())
import hashlib
for source, name in [('port/audio-probe','bin/audio-probe'),('port/ram-init','bin/ram-base-init')]:
    data = Path(source).read_bytes()
    (runtime/name).write_bytes(data)
    m['files'][name] = {'sha256':hashlib.sha256(data).hexdigest(),'mode':0o755,'source':source}
(runtime/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-audio-trace',
    '--init-script','port/audio-test-init',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu',
    '--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf',
    '--audio-runtime-dir',runtime,
    '--audio-topology','out/topology-tb378fc/Lenovo-TB378FC-tplg.bin')
old = json.loads(Path('out/boot-audio-foundation/manifest.json').read_text())
prefix = ('rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 '
          'log_buf_len=2M printk.time=1 tb378fc.stage=1')
assert old['cmdline'].startswith(prefix+' ')
run(sys.executable,'port/package-stage1.py',
    '--kernel','out/kernel-audio-trace/arch/arm64/boot/Image',
    '--dtb','out/abl-audio-trace/erhai-abl.dtb',
    '--mainline-dtb','out/kernel-audio-trace/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb',
    '--ramdisk','out/initramfs-audio-trace/initramfs.cpio.gz',
    '--build-manifest','out/audio-trace-build.json',
    '--extra-cmdline',old['cmdline'][len(prefix)+1:],
    '--output','out/boot-audio-trace','--image-name','boot-tb378fc-audio-trace.img')
