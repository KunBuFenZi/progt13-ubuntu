#!/usr/bin/env python3
"""Reuse the accepted kernel/rootfs; change only the touch IRQ to native rising."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
tree = root / 'out/native-touch-tree67'
tree.mkdir(exist_ok=False)
old = root / 'out/live-audio-tree66/sm8750-lenovo-tb378fc-audio-gpio.dtb'
new = tree / old.name
shutil.copy2(old, new)

def run(*args):
    return subprocess.check_output([str(v) for v in args], text=True)

def nodes(parent='/'):
    for child in run('fdtget', '-l', old, parent).splitlines():
        node = parent.rstrip('/') + '/' + child
        yield node
        yield from nodes(node)

matches = []
for node in nodes():
    props = run('fdtget', '-p', old, node).splitlines()
    if 'compatible' in props and 'lenovo,tb378fc-nvt' in run('fdtget', '-t', 's', old, node, 'compatible'):
        matches.append(node)
assert len(matches) == 1, matches
node = matches[0]
assert run('fdtget', '-t', 'i', old, node, 'interrupts').strip() == '162 8'
run('fdtput', '-t', 'i', new, node, 'interrupts', '162', '1')
assert run('fdtget', '-t', 'i', new, node, 'interrupts').strip() == '162 1'
old_text = run('dtc', '-q', '-I', 'dtb', '-O', 'dts', old)
new_text = run('dtc', '-q', '-I', 'dtb', '-O', 'dts', new)
assert old_text.replace('interrupts = <0xa2 0x08>;', 'interrupts = <0xa2 0x01>;') == new_text
subprocess.run([sys.executable, str(root/'reference-tools/build-erhai-abl-symbols.py'),
    '--mainline-dtb', str(new), '--dtbo-img', str(root/'inputs/dtbo.img'),
    '--base-dir', str(root/'inputs/stock-base'), '--identity-index', '11',
    '--dtc', str(root/'out/kernel-memory/scripts/dtc/dtc'), '--output', str(tree/'abl')], check=True)
build = json.loads((root/'out/live-audio66-build.json').read_text())
build['files'][new.relative_to(root).as_posix()] = {
    'sha256': hashlib.sha256(new.read_bytes()).hexdigest(), 'size': new.stat().st_size}
build['status'] = 'NATIVE_RISING_IRQ_ONLY_NOT_DEVICE_TESTED'
build['delta'] = {'node': node, 'interrupts_before': [162, 8], 'interrupts_after': [162, 1],
    'native_module_sha256': '464d0e81c508e94917728c5026ae4b7c8389710e15e8f6f009eef77962198c6b'}
manifest = root/'out/native-touch67-build.json'
manifest.write_text(json.dumps(build, indent=2) + '\n')
original = json.loads((root/'out/boot-live-audio66/manifest.json').read_text())['cmdline']
prefix = 'rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert original.startswith(prefix)
subprocess.run([sys.executable, str(root/'port/package-stage1.py'),
    '--kernel', str(root/'out/kernel-live-audio66/arch/arm64/boot/Image'),
    '--dtb', str(tree/'abl/erhai-abl.dtb'), '--mainline-dtb', str(new),
    '--ramdisk', str(root/'out/initramfs-live-audio66/initramfs.cpio.gz'),
    '--build-manifest', str(manifest), '--extra-cmdline', original[len(prefix):],
    '--output', str(root/'out/boot-native-touch67'), '--image-name', 'boot-tb378fc-native-touch67.img'], check=True)
