#!/usr/bin/env python3
"""Prove real RAM init serves HTTP while USB setup is deliberately stalled."""
import gzip
from pathlib import Path
import subprocess
import time
import urllib.request
import argparse

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kernel', type=Path, default=ROOT / 'out/kernel-stage1/arch/arm64/boot/Image')
parser.add_argument('--ramdir', type=Path, default=ROOT / 'out/initramfs-stage1')
parser.add_argument('--output', type=Path, default=ROOT / 'out/ram-services-check')
parser.add_argument('--kms-no-device', action='store_true')
args = parser.parse_args()
OUT = args.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)
wrapper = OUT / 'init'
wrapper.write_text('''#!/bin/sh
export PATH=/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
ip link set eth0 up
ip address add 10.0.2.15/24 dev eth0
exec /bin/sh /ram-init
''')
stub = OUT / 'usb-stalled'
stub.write_text('#!/bin/sh\necho DELIBERATELY_STALLED_USB_SETUP\nsleep 120\n')
lines = (args.ramdir / 'cpio-list.txt').read_text().splitlines()
for i, line in enumerate(lines):
    if line.startswith('file /init '):
        lines[i] = f'file /init {wrapper} 0755 0 0'
    elif line.startswith('file /bin/usb-diag '):
        lines[i] = f'file /bin/usb-diag {stub} 0755 0 0'
lines.append(f'file /ram-init {ROOT}/port/ram-init 0755 0 0')
listing = OUT / 'cpio-list.txt'
listing.write_text('\n'.join(lines) + '\n')
cpio = subprocess.check_output([str(ROOT / 'out/kernel-stage1/usr/gen_init_cpio'),
                                '-t', '0', str(listing)])
archive = OUT / 'initramfs.cpio.gz'
archive.write_bytes(gzip.compress(cpio, mtime=0))
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with (OUT / 'qemu.log').open('wb') as log:
    qemu = subprocess.Popen(['qemu-system-aarch64', '-M', 'virt', '-cpu', 'max',
        '-m', '1024', '-smp', '2', '-display', 'none', '-serial', 'stdio',
        '-monitor', 'none', '-no-reboot', '-kernel',
        str(args.kernel), '-initrd', str(archive),
        '-append', 'console=ttyAMA0 rdinit=/init panic=15' + (' tb378fc.kms=1' if args.kms_no_device else ''),
        '-netdev', 'user,id=diag,hostfwd=tcp:127.0.0.1:18081-:8081',
        '-device', 'virtio-net-device,netdev=diag'], stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 40
        while True:
            try:
                with opener.open('http://127.0.0.1:18081/build-id.txt', timeout=1) as response:
                    actual = response.read().decode().strip()
                break
            except OSError:
                assert time.monotonic() < deadline, 'RAM HTTP server did not start'
                time.sleep(1)
        expected = (args.ramdir / 'build-id').read_text().strip()
        assert actual == expected
        with opener.open('http://127.0.0.1:18081/usb-setup.txt', timeout=2) as response:
            assert b'DELIBERATELY_STALLED_USB_SETUP' in response.read()
        while True:
            with opener.open('http://127.0.0.1:18081/dmesg.txt', timeout=2) as response:
                evidence = response.read()
            if b'TB378FC_DIAGNOSTIC_SERVICES_STARTED' in evidence:
                break
            assert time.monotonic() < deadline, 'Missing service-start marker'
            time.sleep(1)
        assert b'Kernel panic' not in evidence
        if args.kms_no_device:
            while True:
                try:
                    with opener.open('http://127.0.0.1:18081/kms.txt', timeout=2) as response:
                        kms = response.read()
                    if b'KMS_EXIT=1' in kms:
                        break
                except OSError:
                    pass
                assert time.monotonic() < deadline, 'KMS failure path did not finish'
                time.sleep(1)
            assert b'KMS_FAIL no KMS device' in kms
            assert b'TB378FC_KMS_ACTIVE' not in kms
            (OUT / 'kms.txt').write_bytes(kms)
        (OUT / 'dmesg.txt').write_bytes(evidence)
        print('RAM_SERVICES_PASS: matching build ID and HTTP logs while USB setup is stalled')
    finally:
        qemu.terminate()
        try:
            qemu.wait(timeout=5)
        except subprocess.TimeoutExpired:
            qemu.kill()
            qemu.wait()
