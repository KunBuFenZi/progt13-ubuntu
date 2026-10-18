#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Verify the public same-slot switcher with regular files, never block devices."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

with tempfile.TemporaryDirectory(prefix='tb378fc-switch-test-') as temporary:
    w = Path(temporary)
    store, devices = w / 'store', w / 'devices'
    store.mkdir()
    devices.mkdir()
    for kind in ['android', 'ubuntu']:
        d = store / kind
        d.mkdir()
        sums = []
        for name, size in [('boot', 1 << 20), ('init_boot', 1 << 19), ('vendor_boot', 1 << 20)]:
            data = bytearray(hashlib.shake_256((kind + name).encode()).digest(size))
            if name == 'boot':
                data[:8] = b'ANDROID!'
                if kind == 'ubuntu':
                    marker = b'tb378fc.stage=1'
                    data[44:44 + len(marker)] = marker
            file = d / (name + '.img')
            file.write_bytes(data)
            sums.append(digest(file) + '  ' + name + '.img\n')
            if kind == 'android':
                shutil.copyfile(file, devices / (name + '_a'))
        (d / 'SHA256SUMS').write_text(''.join(sums))
    prefix = ['sh', str(ROOT / 'switch/tb378fc-switch'), '--store', str(store),
              '--dev-dir', str(devices), '--slot', '_a', '--no-reboot']
    def run(args, good=True):
        r = subprocess.run(prefix + args, capture_output=True, text=True, timeout=30)
        assert (r.returncode == 0) == good, (args, r.stdout, r.stderr)
    before = {p.name: digest(p) for p in devices.iterdir()}
    run(['verify'])
    run(['to-ubuntu', '--dry-run'])
    assert before == {p.name: digest(p) for p in devices.iterdir()}
    run(['to-ubuntu'])
    for file in devices.iterdir():
        assert digest(file) == digest(store / 'ubuntu' / (file.name[:-2] + '.img'))
    run(['to-android'])
    assert before == {p.name: digest(p) for p in devices.iterdir()}
    damaged = store / 'ubuntu/vendor_boot.img'
    saved = damaged.read_bytes()
    damaged.write_bytes(b'broken' + saved[6:])
    run(['to-ubuntu'], False)
    assert before == {p.name: digest(p) for p in devices.iterdir()}
    damaged.write_bytes(saved)
    (store / '.switch-incomplete').write_text('interrupted\n')
    run(['to-ubuntu'], False)
    (store / '.switch-incomplete').unlink()
    run(['stash-android'], False)
    assert not (store / 'android.prev').exists()
    assert not (store / '.android.new').exists()
print('PASS: same-slot roundtrip, dry-run, corruption, interrupted-write and existing-backup rules')
