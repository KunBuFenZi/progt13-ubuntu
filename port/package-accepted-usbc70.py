#!/usr/bin/env python3
"""Preserve accepted USB70 and live fixes in a separate private RAM candidate.

Does not select the relay, reboot the device, flash, or touch tablet storage.
"""
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
parser.add_argument('--revision',choices=['70d','70e','70f'],default='70f')
args = parser.parse_args()
stem = 'usbc'+args.revision
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
base = root/'out/private69/settings-usbc70.tar'
previous = json.loads((root/'out/runtime-usbc70/manifest.json').read_text())
assert sha(base) == previous['settings_sha256']
private = root/'out/private70'
private.mkdir(exist_ok=True)
private.chmod(0o700)
target = private/f'settings-accepted-{stem}.tar'
assert not target.exists()
work = root/f'out/runtime-{stem}'
if work.exists():
    assert not any(work.iterdir()), 'Refusing to reuse a populated candidate'
else:
    work.mkdir()
entries = {}
with tarfile.open(base) as archive:
    for item in archive:
        assert not item.name.startswith('/') and '..' not in Path(item.name).parts
        if item.name in ['etc/systemd/system/tb378fc-ram-expiry.timer',
                         'etc/systemd/system/tb378fc-ram-expiry.service',
                         'etc/systemd/system/timers.target.wants/tb378fc-ram-expiry.timer']:
            continue
        entries[item.name] = (copy.copy(item),archive.extractfile(item).read() if item.isfile() else None)

def add(name,data,mode=0o644):
    item = tarfile.TarInfo(name)
    item.mode = mode
    item.size = len(data)
    entries[name] = (item,data)

for filename in ['tb378fc-wifi-ssh70.py','tb378fc-bluetooth-address68.py']:
    add('usr/local/libexec/'+filename,(root/'port'/filename).read_bytes(),0o755)
flash = root/'out/flash-runtime70'
flash_manifest = json.loads((flash/'manifest.json').read_text())
assert sha(flash/'runtime.tar') == flash_manifest['tar_sha256']
with tarfile.open(flash/'runtime.tar') as archive:
    assert set(archive.getnames()) == set(flash_manifest['files'])
    for item in archive:
        data = archive.extractfile(item).read()
        expected = flash_manifest['files'][item.name]
        assert hashlib.sha256(data).hexdigest() == expected['sha256']
        assert item.mode == expected['mode']
        entries[item.name] = (copy.copy(item),data)
name = 'etc/systemd/system/sockets.target.wants/tb378fc-torch70.socket'
item = tarfile.TarInfo(name)
item.type = tarfile.SYMTYPE
item.mode = 0o777
item.linkname = '../tb378fc-torch70.socket'
entries[name] = (item,None)
# The loader creates the LED class device. A ConditionPathExists on the service
# prevents ExecStartPre from running on the first request after a cold boot.
if args.revision == '70f':
    add('etc/systemd/system/tb378fc-torch70.service',
        (root/'port/torch70/tb378fc-torch70.service').read_bytes())
with target.open('xb') as handle:
    target.chmod(0o600)
    with tarfile.open(fileobj=handle,mode='w') as archive:
        for name,(item,data) in sorted(entries.items()):
            archive.addfile(item,io.BytesIO(data) if data is not None else None)
settings_hash = sha(target)
script = (root/'port/desktop-init').read_text()
assert script.count('@SETTINGS_SHA@') == 1
(work/'init').write_text(script.replace('@SETTINGS_SHA@',settings_hash))
subprocess.run([sys.executable,'port/build-initramfs.py','--output',f'out/initramfs-{stem}',
                '--init-script',str(work/'init'),'--extra-applets',
                'wget sha256sum tar chown switch_root tee seq kill umount cp mv',
                '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
                '--gpu-firmware-dir','diagnostics/firmware/gpu',
                '--wifi-firmware-dir','out/wifi-native-v2',
                '--adsp-firmware-dir','diagnostics/firmware/adsp'],check=True)
build = json.loads((root/'out/runtime-usbc70/build-manifest.json').read_text())
build.update(status='ACCEPTED_USB70_LIVE_FIXES_OFFLINE_NOT_BOOTED',settings_sha256=settings_hash)
(work/'build-manifest.json').write_text(json.dumps(build,indent=2)+'\n')
cmd = json.loads((root/'out/boot-usbc70/manifest.json').read_text())['cmdline']
prefix = 'rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert cmd.startswith(prefix)
subprocess.run([sys.executable,'port/package-stage1.py',
                '--kernel','out/kernel-usbc70b/arch/arm64/boot/Image',
                '--dtb','out/usbc-tree70b/abl/erhai-abl.dtb',
                '--mainline-dtb','out/usbc-tree70b/sm8750-lenovo-tb378fc-usbc70.dtb',
                '--ramdisk',f'out/initramfs-{stem}/initramfs.cpio.gz',
                '--build-manifest',str(work/'build-manifest.json'),
                '--extra-cmdline',cmd[len(prefix):],'--output',f'out/boot-{stem}',
                '--image-name',f'boot-tb378fc-{stem}.img'],check=True)
record = {'status':'PRIVATE_RAM_CANDIDATE_READY_NOT_SELECTED_OR_BOOTED',
          'settings_sha256':settings_hash,'previous_settings_sha256':previous['settings_sha256'],
          'boot_sha256':sha(root/f'out/boot-{stem}/boot-tb378fc-{stem}.img'),
          'build_id':(root/f'out/initramfs-{stem}/build-id').read_text().strip(),
          'kernel_and_dtb':'Unchanged from actually tested USB70b',
          'integrated':['Native USB3/dual-role/DP/WCD AUX',
                        'Wi-Fi SSH absolute argv0',
                        'Bluetooth address asynchronous setup wait',
                        'Default-off native flash and desktop torch with30s auto-off'],
          'removed_test_auto_return_to_android_timer':True,
          'private_pairing_wifi_and_desktop_preserved':True,
          'remaining':['Cold-boot regression','Physical flash confirmation',
                       'Net charging','Microphones','Cameras','60/144Hz','Power/long-run regression'],
          'scope':'Separate RAM boot artifact only; running system and relay unchanged'}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
