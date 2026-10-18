#!/usr/bin/env python3
"""Package camera modules and full static DT on microphone73; never select or boot."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parent.parent; os.chdir(root)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume', action='store_true')
args = parser.parse_args()
work = root / 'out/runtime-camera74'; work.mkdir(exist_ok=args.resume)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
base = root / 'out/private73/settings-microphone73.tar'
assert sha(base) == json.loads((root / 'out/runtime-microphone73/host-verified.json').read_text())['settings_sha256']
entries = {}
with tarfile.open(base) as archive:
    for item in archive:
        assert not item.name.startswith('/') and '..' not in Path(item.name).parts
        entries[item.name] = (copy.copy(item), archive.extractfile(item).read() if item.isfile() else None)

def add(name, data, mode=0o644):
    item = tarfile.TarInfo(name); item.mode = mode; item.size = len(data)
    entries[name] = (item, data)

modules = root / 'out/camera74'
manifest = json.loads((modules / 'manifest.json').read_text())
assert manifest['status'] == 'CAMERA74_MODULES_BUILT_NOT_LOADED'
prefix = 'usr/share/tb378fc/camera74/'
for name, item in manifest['modules'].items():
    assert sha(modules / name) == item['sha256']
    add(prefix + name, (modules / name).read_bytes())
add(prefix + 'manifest.json', (modules / 'manifest.json').read_bytes())
add('usr/local/libexec/tb378fc-camera74.py', (root / 'port/tb378fc-camera74.py').read_bytes(), 0o755)
add('etc/systemd/system/tb378fc-camera74.service', (root / 'port/tb378fc-camera74.service').read_bytes())
item = tarfile.TarInfo('etc/systemd/system/graphical.target.wants/tb378fc-camera74.service')
item.type = tarfile.SYMTYPE; item.linkname = '../tb378fc-camera74.service'; item.mode = 0o777
entries[item.name] = (item, None)
private = root / 'out/private74'; private.mkdir(exist_ok=True); private.chmod(0o700)
settings = private / 'settings-camera74.tar'
if settings.exists():
    assert args.resume
    with tarfile.open(settings) as archive:
        assert set(archive.getnames()) == set(entries)
        for observed in archive:
            expected, data = entries[observed.name]
            assert (observed.type, observed.mode, observed.linkname) == (expected.type, expected.mode, expected.linkname)
            if observed.isfile(): assert archive.extractfile(observed).read() == data
else:
    with settings.open('xb') as handle:
        settings.chmod(0o600)
        with tarfile.open(fileobj=handle, mode='w') as archive:
            for name, (item, data) in sorted(entries.items()): archive.addfile(item, io.BytesIO(data) if data is not None else None)

tree = root / 'out/camera-tree74'
dtb = tree / 'sm8750-lenovo-tb378fc-camera74.dtb'
tree_manifest = json.loads((tree / 'manifest.json').read_text())
assert sha(dtb) == tree_manifest['dtb_sha256']
static = tree / 'static-no-symbols.dtb'; shutil.copy2(dtb, static)
subprocess.run(['fdtput', '-r', str(static), '/__symbols__'], check=True)
if not (tree / 'abl-static/erhai-abl.dtb').exists():
    subprocess.run([sys.executable, 'reference-tools/build-erhai-abl-symbols.py', '--mainline-dtb', str(static),
                    '--dtbo-img', 'inputs/dtbo.img', '--base-dir', 'inputs/stock-base', '--identity-index', '11',
                    '--dtc', 'out/kernel-usbc70b/scripts/dtc/dtc', '--output', str(tree / 'abl-static')], check=True)
init = (root / 'port/desktop-init').read_text(); assert init.count('@SETTINGS_SHA@') == 1
(work / 'init').write_text(init.replace('@SETTINGS_SHA@', sha(settings)))
if not (root / 'out/initramfs-camera74/initramfs.cpio.gz').exists():
    subprocess.run([sys.executable, 'port/build-initramfs.py', '--output', 'out/initramfs-camera74',
                    '--init-script', str(work / 'init'), '--extra-applets', 'wget sha256sum tar chown switch_root tee seq kill umount cp mv',
                    '--touch-firmware', 'diagnostics/firmware/novatek_ts_fw.bin', '--gpu-firmware-dir', 'diagnostics/firmware/gpu',
                    '--wifi-firmware-dir', 'out/wifi-native-v2', '--adsp-firmware-dir', 'diagnostics/firmware/adsp'], check=True)
build = json.loads((root / 'out/runtime-microphone73/build-manifest.json').read_text())
build.update(status='CAMERA74_CANDIDATE_NOT_BOOTED', settings_sha256=sha(settings))
build['files'][dtb.relative_to(root).as_posix()] = {'sha256': sha(dtb), 'size': dtb.stat().st_size}
build['files'][static.relative_to(root).as_posix()] = {'sha256': sha(static), 'size': static.stat().st_size}
(work / 'build-manifest.json').write_text(json.dumps(build, indent=2) + '\n')
cmd = json.loads((root / 'out/boot-microphone73/manifest.json').read_text())['cmdline']
prefix = 'rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert cmd.startswith(prefix)
subprocess.run([sys.executable, 'port/package-stage1.py', '--kernel', 'out/kernel-usbc70b/arch/arm64/boot/Image',
                '--dtb', str(tree / 'abl-static/erhai-abl.dtb'), '--mainline-dtb', str(static),
                '--ramdisk', 'out/initramfs-camera74/initramfs.cpio.gz', '--build-manifest', str(work / 'build-manifest.json'),
                '--extra-cmdline', cmd[len(prefix):], '--output', 'out/boot-camera74',
                '--image-name', 'boot-tb378fc-camera74.img'], check=True)
record = {'status': 'CAMERA74_CANDIDATE_READY_NOT_SELECTED_OR_BOOTED', 'settings_sha256': sha(settings),
          'base_settings_sha256': sha(base), 'boot_sha256': sha(root / 'out/boot-camera74/boot-tb378fc-camera74.img'),
          'dtb_sha256': sha(dtb), 'kernel_image_unchanged': True,
          'build_id': (root / 'out/initramfs-camera74/build-id').read_text().strip(),
          'camera_stream_opened': False, 'microphone_stream_opened': False,
          'remaining': ['Candidate host verification', 'Complete temporary boot', 'Sensor identity and camera capture', 'Camera userspace, lens, flash']}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
