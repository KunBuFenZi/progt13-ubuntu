#!/usr/bin/env python3
"""Add verified read-only UFS discovery to the separate76b RAM boot candidate."""
import copy
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
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
work = root / 'out/runtime-ufs77b'; work.mkdir(exist_ok=False)
private = root / 'out/private77b'; private.mkdir(mode=0o700, exist_ok=False)
base = root / 'out/private76b/settings-refresh76b.tar'
assert sha(base) == '688a5492ae3faa5d7bc4bc0e4bef483fdd09736321eef51596e9069f7ca65668'
entries = {}
with tarfile.open(base) as archive:
    for item in archive:
        entries[item.name] = copy.copy(item), archive.extractfile(item).read() if item.isfile() else None
before = set(entries)

def add(name, data, mode=0o644):
    assert name not in entries
    item = tarfile.TarInfo(name); item.mode, item.size = mode, len(data)
    entries[name] = item, data

stack = json.loads((root / 'out/ufs77-modules/manifest.json').read_text())
overlay = root / 'out/ufs77b-overlay-build'
om = json.loads((overlay / 'manifest.json').read_text())
files = {}
for name in stack['order']:
    p = root / 'out/ufs77-modules' / name
    assert sha(p) == stack['modules'][name]['sha256']
    files[name] = sha(p); add('usr/share/tb378fc/ufs77/' + name, p.read_bytes())
for name, key in [('live-ufs-overlay77.ko', 'module_sha256'), ('tb378fc-ufs77.dtbo', 'overlay_sha256')]:
    p = overlay / name; assert sha(p) == om[key]
    files[name] = sha(p); add('usr/share/tb378fc/ufs77/' + name, p.read_bytes())
runtime = {'files': files, 'module_order': stack['order'], 'external_phandles': om['inputs']['external_phandles'],
           'scope': 'read-only discovery; no mounts or internal writes'}
add('usr/share/tb378fc/ufs77/manifest.json', (json.dumps(runtime, indent=2)+'\n').encode())
add('usr/local/libexec/tb378fc-ufs77.py', (root / 'port/tb378fc-ufs77.py').read_bytes(), 0o755)
add('etc/systemd/system/tb378fc-ufs77.service', (root / 'port/tb378fc-ufs77.service').read_bytes())
add('etc/udev/rules.d/05-tb378fc-ufs77.rules', b'SUBSYSTEM=="block", KERNEL=="sd*", ENV{UDISKS_IGNORE}="1"\n')
link = tarfile.TarInfo('etc/systemd/system/graphical.target.wants/tb378fc-ufs77.service')
link.type = tarfile.SYMTYPE; link.linkname = '/etc/systemd/system/tb378fc-ufs77.service'; link.mode = 0o777
entries[link.name] = link, None
settings = private / 'settings-ufs77b.tar'
with settings.open('xb') as handle:
    settings.chmod(0o600)
    with tarfile.open(fileobj=handle, mode='w') as archive:
        for name, (item, data) in sorted(entries.items()):
            archive.addfile(item, io.BytesIO(data) if data is not None else None)
script = (root / 'port/desktop-init').read_text()
(work / 'init').write_text(script.replace('@SETTINGS_SHA@', sha(settings)))
subprocess.run([sys.executable, 'port/build-initramfs.py', '--output', 'out/initramfs-ufs77b',
                '--init-script', str(work/'init'), '--extra-applets', 'wget sha256sum tar chown switch_root tee seq kill umount cp mv',
                '--touch-firmware', 'diagnostics/firmware/novatek_ts_fw.bin', '--gpu-firmware-dir', 'diagnostics/firmware/gpu',
                '--wifi-firmware-dir', 'out/wifi-native-v2', '--adsp-firmware-dir', 'diagnostics/firmware/adsp'], check=True)
build = json.loads((root / 'out/runtime-refresh76b/build-manifest.json').read_text())
build.update(status='UFS77_READ_ONLY_RUNTIME_INTEGRATED', settings_sha256=sha(settings))
(work/'build-manifest.json').write_text(json.dumps(build, indent=2)+'\n')
old = json.loads((root / 'out/boot-refresh76b/manifest.json').read_text())
prefix = 'rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert old['cmdline'].startswith(prefix)
subprocess.run([sys.executable, 'port/package-stage1.py', '--kernel', 'out/kernel-usbc70b/arch/arm64/boot/Image',
                '--dtb', 'out/recovery-tree75b/abl-static/erhai-abl.dtb',
                '--mainline-dtb', 'out/recovery-tree75b/sm8750-lenovo-tb378fc-recovery75.dtb',
                '--ramdisk', 'out/initramfs-ufs77b/initramfs.cpio.gz', '--build-manifest', str(work/'build-manifest.json'),
                '--extra-cmdline', old['cmdline'][len(prefix):], '--output', 'out/boot-ufs77b',
                '--image-name', 'boot-tb378fc-ufs77b.img'], check=True)
new = json.loads((root / 'out/boot-ufs77b/manifest.json').read_text())
assert all(new['inputs'][k] == old['inputs'][k] for k in ['kernel', 'dtb']) and new['cmdline'] == old['cmdline']
record = {'status':'BUILT_NOT_BOOTED', 'boot_sha256':new['boot_sha256'], 'settings_sha256':sha(settings),
          'build_id':(root/'out/initramfs-ufs77b/build-id').read_text().strip(),
          'scope':'Temporary RAM boot; internal UFS read-only; no automount', 'added_paths':sorted(set(entries)-before),
          'known_remaining':['Cold automatic UFS discovery and refresh76 readiness retry not yet booted'],
          'http_settings_selected':False}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
