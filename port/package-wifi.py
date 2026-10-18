#!/usr/bin/env python3
"""Package a RAM-only PCI/WCN7860 discovery candidate after the Wi-Fi build."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import sys

from importlib.util import module_from_spec, spec_from_file_location

ROOT = Path(__file__).resolve().parent.parent
spec = spec_from_file_location('stage1', ROOT / 'port/package-stage1.py')
stage1 = module_from_spec(spec)
spec.loader.exec_module(stage1)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--baseline-dir', type=Path, default=ROOT / 'out/boot-desktop-awake')
p.add_argument('--ramdisk', type=Path, default=ROOT / 'out/initramfs-desktop-awake/initramfs.cpio.gz')
args = p.parse_args()
build = json.loads((ROOT / 'out/wifi-build.json').read_text())
assert build['status'] == 'BUILD_ONLY_NOT_HARDWARE_TESTED'
for name, record in build['files'].items():
    assert sha(ROOT / name) == record['sha256'], name

baseline = json.loads((args.baseline_dir / 'manifest.json').read_text())
ramdisk = args.ramdisk
assert sha(ramdisk) == baseline['inputs']['ramdisk']['sha256']
assert baseline['cmdline'].startswith(stage1.CMDLINE + ' ')
extra = baseline['cmdline'][len(stage1.CMDLINE) + 1:]
dtb = ROOT / 'out/kernel-wifi/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-wifi.dtb'
abl = ROOT / 'out/abl-wifi'
assert not abl.exists(), 'Refusing to replace an ABL candidate'

run(sys.executable, 'reference-tools/build-erhai-abl-symbols.py',
    '--mainline-dtb', dtb, '--dtbo-img', ROOT / 'inputs/dtbo.img',
    '--base-dir', ROOT / 'inputs/stock-base', '--identity-index', '11',
    '--dtc', ROOT / 'out/kernel-wifi/scripts/dtc/dtc', '--output', abl)
run(sys.executable, 'port/package-stage1.py',
    '--kernel', ROOT / 'out/kernel-wifi/arch/arm64/boot/Image',
    '--dtb', abl / 'erhai-abl.dtb', '--mainline-dtb', dtb,
    '--ramdisk', ramdisk, '--build-manifest', ROOT / 'out/wifi-build.json',
    '--extra-cmdline', extra, '--output', ROOT / 'out/boot-wifi',
    '--image-name', 'boot-tb378fc-wifi-discovery-v2.img')

print('WIFI_DISCOVERY_CANDIDATE_PACKAGED_NO_WIFI_FIRMWARE_INCLUDED')
