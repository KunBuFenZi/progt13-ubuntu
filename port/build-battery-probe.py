#!/usr/bin/env python3
"""Build an isolated battery DT and short RAM trial using the frozen ADSP kernel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

def run(*args):
    subprocess.run([str(a) for a in args], check=True)

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--corrected-power', action='store_true')
p.add_argument('--corrected-current', action='store_true')
args = p.parse_args()
if args.corrected_current:
    args.corrected_power = True
name = 'sm8750-lenovo-tb378fc-battery'
source = Path('port') / (name + '.dts')
destination = Path('out/battery-probe-v3' if args.corrected_current else ('out/battery-probe-v2' if args.corrected_power else 'out/battery-probe'))
destination.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, Path('kernel/arch/arm64/boot/dts/qcom') / source.name)
env = os.environ.copy()
env.update(ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-')
subprocess.run(['make', '-C', 'kernel', 'O=' + str(ROOT/'out/kernel-memory'),
                'qcom/' + name + '.dtb'], env=env, check=True)
dtb = destination / (name + '.dtb')
shutil.copy2(Path('out/kernel-memory/arch/arm64/boot/dts/qcom') / dtb.name, dtb)
manifest = json.loads(Path('out/battery-v2-build.json' if args.corrected_current else ('out/battery-build.json' if args.corrected_power else 'out/adsp-build.json')).read_text())
manifest['status'] = 'BATTERY_PROTOCOL_RAM_PROBE_NOT_DEVICE_TESTED'
for path in [source, dtb, Path(__file__).relative_to(ROOT)]:
    manifest['files'][path.as_posix()] = {
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'size': path.stat().st_size,
    }
build = destination/'build.json'
build.write_text(json.dumps(manifest, indent=2)+'\n')
run(sys.executable, 'reference-tools/build-erhai-abl-symbols.py',
    '--mainline-dtb', dtb, '--dtbo-img', 'inputs/dtbo.img',
    '--base-dir', 'inputs/stock-base', '--identity-index', '11',
    '--dtc', 'out/kernel-memory/scripts/dtc/dtc', '--output', destination/'abl')
old = json.loads(Path('out/boot-adsp-probe/manifest.json').read_text())
prefix = ('rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 '
          'log_buf_len=2M printk.time=1 tb378fc.stage=1')
assert old['cmdline'].startswith(prefix+' ')
run(sys.executable, 'port/package-stage1.py',
    '--kernel', 'out/kernel-battery-v2/arch/arm64/boot/Image' if args.corrected_current else ('out/kernel-battery/arch/arm64/boot/Image' if args.corrected_power else 'out/kernel-adsp/arch/arm64/boot/Image'),
    '--dtb', destination/'abl/erhai-abl.dtb', '--mainline-dtb', dtb,
    '--ramdisk', 'out/initramfs-adsp-probe/initramfs.cpio.gz',
    '--build-manifest', build, '--extra-cmdline', old['cmdline'][len(prefix)+1:],
    '--output', destination/'boot', '--image-name', 'boot-tb378fc-battery-probe-v2.img')
