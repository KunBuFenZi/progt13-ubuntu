#!/usr/bin/env python3
"""Prepare the private USB-C RAM trial, including the latest pairing and desktop."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

root = Path(__file__).resolve().parent.parent
os.chdir(root)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
private = root / 'out/private69'
private.mkdir(exist_ok=True)
private.chmod(0o700)
target = private / 'settings-usbc70.tar'
assert not target.exists()
state = private / 'user-state69.tar.gz'
assert sha(state) == state.with_name('user-state69.sha256').read_text().split()[0]
base = root / 'out/peripherals-package68h'
proof = json.loads((base / 'manifest.json').read_text())
assert sha(base / 'settings.tar') == proof['settings_sha256']
entries = {}
with tarfile.open(base / 'settings.tar') as archive:
    for item in archive:
        data = archive.extractfile(item).read() if item.isfile() else None
        if item.isfile():
            assert hashlib.sha256(data).hexdigest() == proof['files_sha256'][item.name]
        entries[item.name] = (copy.copy(item), data)
with tarfile.open(state) as archive:
    for item in archive:
        name = item.name
        assert not name.startswith('/') and '..' not in Path(name).parts
        assert name.startswith(('var/lib/bluetooth', 'etc/NetworkManager/system-connections',
                                'home/pad/.config/dconf')) or name in ['home/pad/.config/monitors.xml', 'user-settings69.dconf']
        assert item.isdir() or item.isfile()
        if name == 'user-settings69.dconf':
            continue
        entries[name] = (copy.copy(item), archive.extractfile(item).read() if item.isfile() else None)

def add(name, data, mode=0o644):
    if isinstance(data, str):
        data = data.encode()
    item = tarfile.TarInfo(name); item.mode = mode; item.mtime = int(time.time())
    item.size = len(data)
    entries[name] = (item, data)

add('usr/local/libexec/tb378fc-wifi-ssh70.py', (root / 'port/tb378fc-wifi-ssh70.py').read_bytes(), 0o755)
add('etc/systemd/system/tb378fc-wifi-ssh70.service', '''[Unit]
Description=TB378FC key-only wireless RAM diagnostics
After=NetworkManager.service
[Service]
ExecStart=/usr/bin/python3 /usr/local/libexec/tb378fc-wifi-ssh70.py
Restart=no
''')
# Use the unchanged native module ABI; update depmod's builtin list to kernel70b.
kernel = root / 'out/kernel-usbc70b'
release = (kernel / 'include/config/kernel.release').read_text().strip()
module_root = 'usr/lib/modules/' + release
for name in ['modules.builtin', 'modules.builtin.modinfo']:
    add(module_root + '/' + name, (kernel / name).read_bytes())
work = root / 'out/runtime-usbc70'
work.mkdir(exist_ok=False)
stage = work / 'module-root'
(stage / module_root).mkdir(parents=True)
(stage / 'lib').symlink_to('usr/lib', target_is_directory=True)
for name, (item, data) in list(entries.items()):
    if name.startswith(module_root + '/') and item.isfile():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
subprocess.run(['depmod', '-b', str(stage), '-F', str(kernel / 'System.map'), release], check=True)
for path in (stage / module_root).glob('modules.*'):
    add(module_root + '/' + path.name, path.read_bytes())
with target.open('xb') as handle:
    target.chmod(0o600)
    with tarfile.open(fileobj=handle, mode='w') as archive:
        for name, (item, data) in sorted(entries.items()):
            archive.addfile(item, io.BytesIO(data) if data is not None else None)
settings_hash = sha(target)
script = (root / 'port/desktop-init').read_text()
assert script.count('@SETTINGS_SHA@') == 1
(work / 'init').write_text(script.replace('@SETTINGS_SHA@', settings_hash))
subprocess.run([sys.executable, 'port/build-initramfs.py', '--output', 'out/initramfs-usbc70',
                '--init-script', str(work / 'init'), '--extra-applets',
                'wget sha256sum tar chown switch_root tee seq kill umount cp mv',
                '--touch-firmware', 'diagnostics/firmware/novatek_ts_fw.bin',
                '--gpu-firmware-dir', 'diagnostics/firmware/gpu',
                '--wifi-firmware-dir', 'out/wifi-native-v2',
                '--adsp-firmware-dir', 'diagnostics/firmware/adsp'], check=True)
build = json.loads((root / 'out/peripherals-package68d/build-manifest.json').read_text())
tree = root / 'out/usbc-tree70b/sm8750-lenovo-tb378fc-usbc70.dtb'
image = kernel / 'arch/arm64/boot/Image'
for path in [image, tree]:
    build['files'][path.relative_to(root).as_posix()] = {'sha256': sha(path), 'size': path.stat().st_size}
build.update(status='USB_C70_RAM_CANDIDATE_NOT_BOOTED', settings_sha256=settings_hash)
(work / 'build-manifest.json').write_text(json.dumps(build, indent=2) + '\n')
cmd = json.loads((root / 'out/boot-peripherals68/manifest.json').read_text())['cmdline']
prefix = 'rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert cmd.startswith(prefix)
subprocess.run([sys.executable, 'port/package-stage1.py', '--kernel', str(image),
                '--dtb', 'out/usbc-tree70b/abl/erhai-abl.dtb', '--mainline-dtb', str(tree),
                '--ramdisk', 'out/initramfs-usbc70/initramfs.cpio.gz',
                '--build-manifest', str(work / 'build-manifest.json'),
                '--extra-cmdline', cmd[len(prefix):], '--output', 'out/boot-usbc70',
                '--image-name', 'boot-tb378fc-usbc70.img'], check=True)
record = {'status': 'PRIVATE_RAM_CANDIDATE_READY_NOT_SELECTED_OR_BOOTED',
          'settings_sha256': settings_hash, 'boot_sha256': sha('out/boot-usbc70/boot-tb378fc-usbc70.img'),
          'build_id': (root / 'out/initramfs-usbc70/build-id').read_text().strip(),
          'latest_private_state_preserved': True, 'panel_120_only': True,
          'wireless_ssh_policy': 'Manual start after USB pinned-key verification; same key, authorized WLAN only',
          'scope': 'USB-C/negotiated input current candidate. No device flash or storage mounts.'}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
