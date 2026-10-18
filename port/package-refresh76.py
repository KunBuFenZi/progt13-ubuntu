#!/usr/bin/env python3
"""Freeze verified live DFPS support into a separate RAM boot candidate."""
import copy
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parent.parent
os.chdir(root)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', choices=['76b'], default='76b')
revision = parser.parse_args().revision
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
work = root / ('out/runtime-refresh' + revision)
work.mkdir(exist_ok=False)
private = root / ('out/private' + revision)
private.mkdir(mode=0o700, exist_ok=False)
accepted = json.loads((root / 'out/device-tests/20261018-refresh76/accepted-live76.json').read_text())
assert accepted['status'] == 'LIVE_CONTINUOUS_60_120_144_AND_DPMS_VERIFIED'
assert accepted['taint'] == 4608 and not accepted['faults']
base = root / 'out/private75/settings-recovery75b.tar'
assert sha(base) == '0152e316c3d69ec8cc9d26125e8f36be601788c3145e3056a001b34a40392ca1'
entries = {}
with tarfile.open(base) as archive:
    for item in archive:
        entries[item.name] = (copy.copy(item), archive.extractfile(item).read() if item.isfile() else None)
before = set(entries)


def add(name, data, mode=0o644):
    assert not name.startswith('/') and '..' not in Path(name).parts
    assert name not in entries
    item = tarfile.TarInfo(name)
    item.mode, item.size = mode, len(data)
    entries[name] = item, data


module = root / 'out/refresh-live76/refresh-live76.ko'
runtime = json.loads((root / 'out/refresh-live76/manifest.json').read_text())
assert sha(module) == runtime['module_sha256'] == 'b9b332a57677cb1ccd4496df8e981142b34a9a9318382f90531e6ff580d017cd'
runtime.update(status='LIVE_CONTINUOUS_REFRESH_VERIFIED',
               acceptance_sha256=sha(root / 'out/device-tests/20261018-refresh76/accepted-live76.json'))
add('usr/share/tb378fc/refresh76/refresh-live76.ko', module.read_bytes())
add('usr/share/tb378fc/refresh76/manifest.json', (json.dumps(runtime, indent=2) + '\n').encode())
add('usr/local/libexec/tb378fc-refresh76.py', (root / 'port/tb378fc-refresh76.py').read_bytes(), 0o755)
add('etc/systemd/system/tb378fc-refresh76.service', (root / 'port/tb378fc-refresh76.service').read_bytes())
link = tarfile.TarInfo('etc/systemd/system/graphical.target.wants/tb378fc-refresh76.service')
link.type = tarfile.SYMTYPE
link.linkname = '/etc/systemd/system/tb378fc-refresh76.service'
link.mode = 0o777
entries[link.name] = link, None
assert len(set(entries) - before) == 5
settings = private / ('settings-refresh' + revision + '.tar')
with settings.open('xb') as handle:
    settings.chmod(0o600)
    with tarfile.open(fileobj=handle, mode='w') as archive:
        for name, (item, data) in sorted(entries.items()):
            archive.addfile(item, io.BytesIO(data) if data is not None else None)

script = (root / 'port/desktop-init').read_text()
assert script.count('@SETTINGS_SHA@') == 1
(work / 'init').write_text(script.replace('@SETTINGS_SHA@', sha(settings)))
subprocess.run([sys.executable, 'port/build-initramfs.py', '--output', 'out/initramfs-refresh' + revision,
                '--init-script', str(work / 'init'), '--extra-applets', 'wget sha256sum tar chown switch_root tee seq kill umount cp mv',
                '--touch-firmware', 'diagnostics/firmware/novatek_ts_fw.bin', '--gpu-firmware-dir', 'diagnostics/firmware/gpu',
                '--wifi-firmware-dir', 'out/wifi-native-v2', '--adsp-firmware-dir', 'diagnostics/firmware/adsp'], check=True)
build = json.loads((root / 'out/runtime-recovery75b/build-manifest.json').read_text())
build.update(status='REFRESH76_VERIFIED_LIVE_RUNTIME_INTEGRATED', settings_sha256=sha(settings))
(work / 'build-manifest.json').write_text(json.dumps(build, indent=2) + '\n')
old = json.loads((root / 'out/boot-recovery75b/manifest.json').read_text())
baseline = 'rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert old['cmdline'].startswith(baseline)
subprocess.run([sys.executable, 'port/package-stage1.py', '--kernel', 'out/kernel-usbc70b/arch/arm64/boot/Image',
                '--dtb', 'out/recovery-tree75b/abl-static/erhai-abl.dtb',
                '--mainline-dtb', 'out/recovery-tree75b/sm8750-lenovo-tb378fc-recovery75.dtb',
                '--ramdisk', 'out/initramfs-refresh' + revision + '/initramfs.cpio.gz', '--build-manifest', str(work / 'build-manifest.json'),
                '--extra-cmdline', old['cmdline'][len(baseline):], '--output', 'out/boot-refresh' + revision,
                '--image-name', 'boot-tb378fc-refresh' + revision + '.img'], check=True)
new = json.loads((root / ('out/boot-refresh' + revision + '/manifest.json')).read_text())
assert all(new['inputs'][n] == old['inputs'][n] for n in ['kernel', 'dtb'])
assert new['cmdline'] == old['cmdline']
record = {'status': 'BUILT_NOT_BOOTED', 'boot_sha256': new['boot_sha256'],
          'settings_sha256': sha(settings), 'build_id': (root / ('out/initramfs-refresh' + revision + '/build-id')).read_text().strip(),
          'base75b_settings_unchanged': True, 'added_paths': sorted(set(entries) - before),
          'kernel_image_and_dt_unchanged': True, 'scope': 'Temporary fastboot boot RAM system; no persistent storage',
          'modes': [60, 120, 144], 'startup_default_hz': 120,
          'no_hd_camera_entry': True, 'media_discovery_idle_restart_at_most_once': True,
          'live_acceptance_boot_id': accepted['boot_id'],
          'known_remaining': ['Bounded cold display readiness retry has not yet been cold booted']}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
