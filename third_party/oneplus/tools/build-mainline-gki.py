#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Package a mainline candidate as the GKI boot triplet this device expects.

The tablet's stock boot chain is Android header v4: the boot partition holds a
kernel and nothing else (ramdisk_size = 0), the generic ramdisk lives in
init_boot, and vendor_boot carries the vendor ramdisk plus the dtb. A header v2
image with its own ramdisk and dtb works for `fastboot boot`, which parses one
downloaded image on its own, but a flashed slot is composed from the three
partitions instead -- so a persistent install has to be shipped the same way
the stock images are.

Layout produced here:

    boot_b        v4, kernel only, carrying our kernel command line
    init_boot_b   v4, ramdisk only, an empty cpio so nothing overrides us
    vendor_boot_b v4, vendor ramdisk = our initramfs, plus the erhai dtb

The bootloader concatenates the vendor ramdisk and the generic ramdisk, so the
initramfs goes in vendor_boot and init_boot stays empty. Sizes are checked
against the real partitions before anything is written.

The dtb must carry an ABL overlay sink (tools/build-erhai-abl-symbols.py);
its layout is read back from the dtb and recorded. The legacy root-level
layout is only taken with --legacy-sink, since it holds back sync_state() and
is kept for fallback and comparison, not for a daily install.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

from lib.abl_layout import LayoutError, add_arguments as add_layout_arguments, \
    check_choice, sink_layout
from lib.boot_profiles import CMDLINE, PROFILE_EXTRA

REPO = Path(__file__).resolve().parent.parent
if (REPO.parent.parent / 'AGENTS.md').is_file() and (REPO.parent.parent / 'kernel/linux').is_dir():
    WS = Path(os.environ.get('ERHAI_WORKSPACE', REPO.parent.parent)).resolve()
else:
    WS = Path(os.environ.get('ERHAI_WORKSPACE', str(REPO))).resolve()
KERNEL_GIT = WS / 'kernel/linux'
DEFAULT_OUT = WS / 'out/kernel-firstboot'
MKBOOT = Path(os.environ.get('MKBOOTIMG', str(WS / 'cache/tools/mkbootimg.py')))

# Partition capacities on this device, from `fastboot getvar partition-size:*`.
CAPACITY = {
    'boot': 0x6000000,        # 96 MiB
    'init_boot': 0x800000,    # 8 MiB
    'vendor_boot': 0x6000000,  # 96 MiB
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def empty_cpio_gz(path):
    """A valid newc cpio holding only the TRAILER!!! entry, gzipped.

    init_boot must be a well-formed image, but anything in its ramdisk would be
    unpacked over ours, so it carries an empty archive.
    """
    name = b'TRAILER!!!\x00'
    header = b'070701' + b''.join(
        b'%08X' % v for v in (
            0,          # ino
            0,          # mode
            0, 0,       # uid, gid
            1,          # nlink
            0,          # mtime
            0,          # filesize
            0, 0,       # devmajor, devminor
            0, 0,       # rdevmajor, rdevminor
            len(name),  # namesize
            0,          # check
        ))
    blob = header + name
    blob += b'\x00' * (-len(blob) % 4)
    # mtime=0 so the archive is byte-for-byte reproducible.
    with open(path, 'wb') as f:
        with gzip.GzipFile(fileobj=f, mode='wb', mtime=0) as gz:
            gz.write(blob)
    return path


def boot_header(path):
    """Read back what we wrote, so the manifest records the real geometry."""
    data = Path(path).read_bytes()[:4096]
    if data[:8] == b'VNDRBOOT':
        ver, page = struct.unpack('<II', data[8:16])
        vendor_ramdisk_size = struct.unpack('<I', data[24:28])[0]
        hdr_size, dtb_size = struct.unpack('<II', data[2096:2104])
        entries = struct.unpack('<I', data[2116:2120])[0] if ver >= 4 else 0
        return {'type': 'vendor_boot', 'header_version': ver, 'page_size': page,
                'vendor_ramdisk_size': vendor_ramdisk_size, 'dtb_size': dtb_size,
                'vendor_ramdisk_table_entries': entries}
    if data[:8] != b'ANDROID!':
        return {'type': 'unknown'}
    ver = struct.unpack('<I', data[40:44])[0]
    kernel_size, ramdisk_size = struct.unpack('<II', data[8:16])
    cmdline = data[44:44 + 1536].rstrip(b'\x00').decode(errors='replace')
    return {'type': 'boot', 'header_version': ver, 'kernel_size': kernel_size,
            'ramdisk_size': ramdisk_size, 'cmdline': cmdline}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    parser.add_argument('--kernel-out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--initramfs', type=Path,
                        default=WS / 'out/initramfs-dev/initramfs-ncm.cpio.gz')
    parser.add_argument('--dtb', type=Path)
    parser.add_argument('--cmdline-extra', default='',
                        help='Appended to the standard cmdline')
    parser.add_argument('--profile', choices=('persistent',),
                        help='Append the pinned persistent-install cmdline')
    add_layout_arguments(parser)
    args = parser.parse_args()

    cmdline = CMDLINE
    if args.profile == 'persistent':
        cmdline += ' ' + PROFILE_EXTRA[args.profile]
    if args.cmdline_extra.strip():
        cmdline += ' ' + args.cmdline_extra.strip()

    kout = args.kernel_out.resolve()
    image = kout / 'arch/arm64/boot/Image'
    dtb = args.dtb or kout / 'arch/arm64/boot/dts/qcom/sm8750-erhai.dtb'
    initramfs = args.initramfs.resolve()
    for path in (image, dtb, initramfs):
        if not path.is_file():
            parser.error(f'Missing input: {path}')
    try:
        layout = check_choice(sink_layout(dtb.read_bytes()), args.sink_layout)
    except LayoutError as error:
        parser.error(f'{dtb}: {error}')

    head = subprocess.run(['git', '-C', str(KERNEL_GIT), 'rev-parse', 'HEAD'],
                          capture_output=True, check=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', '-C', str(KERNEL_GIT), 'status', '--porcelain'],
                           capture_output=True, check=True, text=True).stdout.strip()
    if dirty:
        parser.error(f'Kernel tree is dirty; commit first so the candidate '
                     f'identifies real code:\n{dirty}')

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    empty = empty_cpio_gz(out / 'init_boot-ramdisk.cpio.gz')

    boot = out / 'boot.img'
    init_boot = out / 'init_boot.img'
    vendor_boot = out / 'vendor_boot.img'

    subprocess.run(['python3', str(MKBOOT), '--header_version', '4',
                    '--pagesize', '4096', '--kernel', str(image),
                    '--cmdline', cmdline, '--os_version', '15.0.0',
                    '--os_patch_level', '2026-07', '--output', str(boot)], check=True)
    subprocess.run(['python3', str(MKBOOT), '--header_version', '4',
                    '--pagesize', '4096', '--ramdisk', str(empty),
                    '--os_version', '15.0.0', '--os_patch_level', '2026-07',
                    '--output', str(init_boot)], check=True)
    subprocess.run(['python3', str(MKBOOT), '--header_version', '4',
                    '--pagesize', '4096', '--vendor_ramdisk', str(initramfs),
                    '--dtb', str(dtb), '--vendor_cmdline', '',
                    '--ramdisk_offset', '0x01000000', '--dtb_offset', '0x01f00000',
                    '--tags_offset', '0x00000100', '--base', '0',
                    '--kernel_offset', '0x00008000',
                    '--vendor_boot', str(vendor_boot)], check=True)

    parts = {'boot': boot, 'init_boot': init_boot, 'vendor_boot': vendor_boot}
    outputs = {}
    for name, path in parts.items():
        size = path.stat().st_size
        cap = CAPACITY[name]
        if size > cap:
            parser.error(f'{path.name} is {size} bytes, larger than the '
                         f'{name} partition ({cap} bytes)')
        outputs[name] = {'file': path.name, 'size': size, 'capacity': cap,
                         'sha256': sha(path), 'header': boot_header(path)}

    # The whole point of the triplet is the split; assert it rather than trust it.
    assert outputs['boot']['header']['ramdisk_size'] == 0, 'boot.img must be kernel-only'
    assert outputs['boot']['header']['header_version'] == 4
    assert outputs['vendor_boot']['header']['dtb_size'] > 0, 'vendor_boot needs the dtb'
    assert outputs['vendor_boot']['header']['vendor_ramdisk_size'] > 0

    manifest = {'status': 'OFFLINE_CANDIDATE_NOT_DEVICE_TESTED',
                'layout': 'gki-v4-triplet',
                'kernel_commit': head, 'kernel_out': str(kout),
                'cmdline': cmdline,
                'inputs_sha256': {'Image': sha(image), 'sm8750-erhai.dtb': sha(dtb),
                                  'initramfs.cpio.gz': sha(initramfs),
                                  'init_boot-ramdisk.cpio.gz': sha(empty)},
                'abl_sink_layout': layout,
                'outputs': outputs,
                'scope': 'flash to boot_b / init_boot_b / vendor_boot_b and switch slot; '
                         'the kernel needs CONFIG_BOOT_CONFIG for the bootconfig the '
                         'bootloader appends on this path.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'kernel_commit': head,
                      'boot': outputs['boot']['sha256'],
                      'init_boot': outputs['init_boot']['sha256'],
                      'vendor_boot': outputs['vendor_boot']['sha256']}, indent=2))


if __name__ == '__main__':
    main()
