#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Add AVB hash footers to a boot triplet so the bootloader will accept it.

`vbmeta` on this device describes `boot` as a *chain partition* and
`init_boot` / `vendor_boot` with *hash descriptors*.  libavb therefore reads a
vbmeta structure out of the tail of the boot partition on every cold boot.  An
image without that footer is not a verification failure but malformed
metadata, which the bootloader refuses even when it is unlocked -- it drops to
fastboot instead of booting, for a plain Android boot as much as for ours.  So
every image written into one of these partitions needs a footer, self-signed
included: an unlocked device tolerates an unknown key, it does not tolerate a
missing structure.

The footer lives in the last pages of the *partition*, not of the image, so
avbtool pads each image out to the full partition size here and the installer
writes whole partitions.

Partition sizes and rollback indices are read from the stock images of the
firmware the device is running, so a mismatch is reported instead of guessed.

The hash salt is derived from the image rather than left to avbtool's default
of /dev/urandom, so signing the same triplet twice produces the same bytes.
Packaging reads those bytes back as an identity: an image that changes only
because it was signed again is an image nobody can tell apart from a real
change.

    sign-boot-triplet.py --triplet out/mainline-gki-mNNN \\
        --stock cache/stock-c34/images --key private/avb/erhai-test-rsa4096.pem \\
        --output out/mainline-gki-mNNN-avb

Needs avbtool: --avbtool, $AVBTOOL, or `avbtool` on PATH.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

PARTITIONS = ('boot', 'init_boot', 'vendor_boot')


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def avbtool(tool, *args):
    command = [*tool, *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'avbtool failed: {" ".join(command)}\n'
                         f'{result.stderr or result.stdout}')
    return result.stdout


def info_image(tool, path):
    """Partition size, rollback index and algorithm of an already-signed image."""
    text = avbtool(tool, 'info_image', '--image', str(path))
    fields = {}
    for key, pattern in (('image_size', r'^Image size:\s+(\d+) bytes'),
                         ('original_size', r'^Original image size:\s+(\d+) bytes'),
                         ('rollback_index', r'^Rollback Index:\s+(\d+)'),
                         ('algorithm', r'^Algorithm:\s+(\S+)')):
        match = re.search(pattern, text, re.M)
        fields[key] = match.group(1) if match else None
    for key in ('image_size', 'original_size', 'rollback_index'):
        if fields[key] is not None:
            fields[key] = int(fields[key])
    match = re.search(r'Partition Name:\s+(\S+)', text)
    fields['partition_name'] = match.group(1) if match else None
    return fields


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--triplet', type=Path, required=True,
                        help='Directory holding boot.img / init_boot.img / vendor_boot.img')
    parser.add_argument('--stock', type=Path, required=True,
                        help='Stock images of the running firmware, for the '
                             'partition sizes and rollback indices to match')
    parser.add_argument('--key', type=Path, required=True,
                        help='RSA-4096 private key in PEM form (kept out of the repo)')
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    parser.add_argument('--algorithm', default='SHA256_RSA4096')
    parser.add_argument('--avbtool', default=os.environ.get('AVBTOOL', 'avbtool'))
    args = parser.parse_args()

    tool = [args.avbtool]
    if args.avbtool.endswith('.py'):
        tool = [sys.executable, args.avbtool]
    if shutil.which(tool[-1]) is None and not Path(tool[-1]).is_file():
        parser.error(f'avbtool not found: {args.avbtool}')

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)

    manifest = {'status': 'OFFLINE_CANDIDATE_NOT_DEVICE_TESTED',
                'layout': 'gki-v4-triplet-avb',
                'avbtool_sha256': sha256_file(tool[-1]),
                'key_sha256': sha256_file(args.key),
                'algorithm': args.algorithm,
                'partitions': {}}
    source_manifest = args.triplet / 'manifest.json'
    if source_manifest.is_file():
        manifest['source_manifest'] = json.loads(source_manifest.read_text())

    for name in PARTITIONS:
        source = (args.triplet / f'{name}.img').resolve()
        reference = (args.stock / f'{name}.img').resolve()
        if not source.is_file():
            parser.error(f'missing candidate image: {source}')
        if not reference.is_file():
            parser.error(f'missing stock reference: {reference}')
        stock = info_image(tool, reference)
        if stock['partition_name'] != name or stock['image_size'] is None:
            parser.error(f'{reference} carries no usable {name} hash footer')
        target = out / f'{name}.img'
        shutil.copyfile(source, target)
        # Deterministic salt: avbtool would otherwise draw 32 random bytes and
        # the same input would sign to a different image every time.
        salt = hashlib.sha256(b'erhai-avb-salt\x00' + name.encode() + b'\x00'
                              + bytes.fromhex(sha256_file(source))).hexdigest()
        avbtool(tool, 'add_hash_footer', '--image', str(target),
                '--partition_name', name,
                '--partition_size', str(stock['image_size']),
                '--rollback_index', str(stock['rollback_index']),
                '--salt', salt,
                '--algorithm', args.algorithm, '--key', str(args.key))
        signed = info_image(tool, target)
        entry = {'input': str(source.name), 'input_sha256': sha256_file(source),
                 'input_bytes': source.stat().st_size,
                 'footer': {'partition_name': name,
                            'partition_size': stock['image_size'],
                            'rollback_index': stock['rollback_index'],
                            'salt': salt,
                            'algorithm': args.algorithm},
                 'stock_reference': {'file': str(reference.name),
                                     'sha256': sha256_file(reference),
                                     'partition_size': stock['image_size'],
                                     'rollback_index': stock['rollback_index'],
                                     'algorithm': stock['algorithm']},
                 'output': target.name, 'output_bytes': target.stat().st_size,
                 'output_sha256': sha256_file(target),
                 'verified': signed}
        if target.stat().st_size != stock['image_size']:
            parser.error(f'{target} is {target.stat().st_size} bytes, not the '
                         f'{stock["image_size"]}-byte partition size')
        if signed['original_size'] != source.stat().st_size:
            parser.error(f'{target}: footer records {signed["original_size"]} '
                         f'image bytes, the input is {source.stat().st_size}')
        manifest['partitions'][name] = entry

    checksums = ''.join(f'{manifest["partitions"][n]["output_sha256"]}  {n}.img\n'
                        for n in PARTITIONS)
    (out / 'SHA256SUMS').write_text(checksums)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(checksums, end='')


if __name__ == '__main__':
    main()
