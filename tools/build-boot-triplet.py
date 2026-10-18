#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build and AVB-sign the same GKI-v4 layout as the tested Lenovo installation."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
CMDLINE = ('rdinit=/init panic=120 mem_sleep_default=s2idle loglevel=3 log_buf_len=2M '
           'printk.time=1 tb378fc.stage=1 maxcpus=1 nr_cpus=8 earlycon=tb378fb keep_bootcon '
           'clk_ignore_unused pd_ignore_unused regulator_ignore_unused arm-smmu.disable_bypass=0 '
           'drm_kms_helper.fbdev_emulation=0 tb378fc.usb=rndis systemd.unit=graphical.target')

def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['kernel', 'dtb', 'initramfs', 'stock', 'key', 'mkbootimg', 'avbtool', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--cmdline', default=CMDLINE)
    p.add_argument('--os-version', default='15.0.0')
    p.add_argument('--os-patch-level', default='2026-07')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    trailer = b'TRAILER!!!\0'
    empty = b'070701' + b''.join(b'%08X' % v for v in (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(trailer), 0)) + trailer
    empty += b'\0' * (-len(empty) % 4)
    ramdisk = a.output / 'empty.cpio.gz'
    ramdisk.write_bytes(gzip.compress(empty, mtime=0))
    mk = [sys.executable, str(a.mkbootimg.resolve()), '--header_version', '4', '--pagesize', '4096']
    metadata = ['--os_version', a.os_version, '--os_patch_level', a.os_patch_level]
    subprocess.run(mk + metadata + ['--kernel', str(a.kernel.resolve()), '--cmdline', a.cmdline,
                                   '--output', str(a.output / 'boot.img')], check=True)
    subprocess.run(mk + metadata + ['--ramdisk', str(ramdisk), '--output', str(a.output / 'init_boot.img')], check=True)
    subprocess.run(mk + ['--vendor_ramdisk', str(a.initramfs.resolve()), '--dtb', str(a.dtb.resolve()),
                         '--vendor_cmdline', '', '--base', '0', '--kernel_offset', '0x8000',
                         '--ramdisk_offset', '0x1000000', '--tags_offset', '0x100', '--dtb_offset', '0x1f00000',
                         '--vendor_boot', str(a.output / 'vendor_boot.img')], check=True)
    # Signing is the pinned upstream implementation: derive geometry and rollback
    # from each owner's original images, not another tablet's saved footer.
    signed = a.output / 'signed'
    subprocess.run([sys.executable, str(ROOT / 'third_party/oneplus/tools/sign-boot-triplet.py'),
                    '--triplet', str(a.output), '--stock', str(a.stock.resolve()), '--key', str(a.key.resolve()),
                    '--avbtool', str(a.avbtool.resolve()), '--output', str(signed)], check=True)
    result = {'layout': 'GKI-v4-AVB-same-slot', 'device': 'Lenovo TB378FC', 'cmdline': a.cmdline,
              'os_version': a.os_version, 'os_patch_level': a.os_patch_level,
              'inputs': {n: digest(getattr(a, n)) for n in ['kernel', 'dtb', 'initramfs']},
              'partitions': {n: {'sha256': digest(signed / (n + '.img')), 'bytes': (signed / (n + '.img')).stat().st_size}
                             for n in ['boot', 'init_boot', 'vendor_boot']}}
    (a.output / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Signed images:', signed)

if __name__ == '__main__':
    main()
