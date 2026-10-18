#!/usr/bin/env python3
"""Prepare a private next RAM-boot payload preserving this unit's pairing/Wi-Fi."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

root=Path(__file__).resolve().parent.parent
os.chdir(root)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=Path('out/peripherals-package68h')
manifest=json.loads((base/'manifest.json').read_text())
assert sha(base/'settings.tar')==manifest['settings_sha256']
private=Path('out/private68');private.mkdir(exist_ok=True);private.chmod(0o700)
target=private/'settings-paired68h.tar'
assert not target.exists()
entries={}
with tarfile.open(base/'settings.tar') as archive:
    for item in archive:
        assert not item.name.startswith('/') and '..' not in Path(item.name).parts
        data=archive.extractfile(item).read() if item.isfile() else None
        if item.isfile():assert hashlib.sha256(data).hexdigest()==manifest['files_sha256'][item.name]
        entries[item.name]=(copy.copy(item),data)
allowed='var/lib/bluetooth/02:18:62:20:BB:9F'
wifi='etc/NetworkManager/system-connections/tb378fc-authorized-test.nmconnection'
with tarfile.open(private/'user-state68.tar.gz') as archive:
    for item in archive:
        assert item.name==wifi or item.name==allowed+'/settings' or item.name.startswith(allowed+'/90:F2:60:BF:F0:B4')
        assert item.isdir() or item.isfile()
        item=copy.copy(item);item.uid=item.gid=0;item.uname=item.gname='root'
        item.mode=0o700 if item.isdir() else 0o600
        entries[item.name]=(item,archive.extractfile(item).read() if item.isfile() else None)
for name in ('var/lib/bluetooth',allowed,allowed+'/90:F2:60:BF:F0:B4'):
    item=tarfile.TarInfo(name);item.type=tarfile.DIRTYPE;item.mode=0o700
    entries[name]=(item,None)
with target.open('xb') as handle:
    target.chmod(0o600)
    with tarfile.open(fileobj=handle,mode='w') as archive:
        for name,(item,data) in sorted(entries.items()):
            archive.addfile(item,io.BytesIO(data) if data is not None else None)
work=Path('out/runtime-integrated68h');work.mkdir(exist_ok=False)
script=Path('port/desktop-init').read_text()
assert script.count('@SETTINGS_SHA@')==1
(work/'init').write_text(script.replace('@SETTINGS_SHA@',sha(target)))
subprocess.run([sys.executable,'port/build-initramfs.py','--output','out/initramfs-runtime68h','--init-script',str(work/'init'),
    '--extra-applets','wget sha256sum tar chown switch_root tee seq kill umount cp mv',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin','--gpu-firmware-dir','diagnostics/firmware/gpu',
    '--wifi-firmware-dir','out/wifi-native-v2','--adsp-firmware-dir','diagnostics/firmware/adsp'],check=True)
build=json.loads(Path('out/peripherals-package68d/build-manifest.json').read_text())
build.update(status='INTEGRATED_RUNTIME68H_OFFLINE_NOT_COLD_BOOT_TESTED',settings_sha256=sha(target))
(work/'build-manifest.json').write_text(json.dumps(build,indent=2)+'\n')
cmd=json.loads(Path('out/boot-peripherals68/manifest.json').read_text())['cmdline']
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert cmd.startswith(prefix)
subprocess.run([sys.executable,'port/package-stage1.py','--kernel','out/kernel-peripherals68/arch/arm64/boot/Image',
    '--dtb','out/peripherals-tree68/abl/erhai-abl.dtb','--mainline-dtb','out/peripherals-tree68/sm8750-lenovo-tb378fc-peripherals.dtb',
    '--ramdisk','out/initramfs-runtime68h/initramfs.cpio.gz','--build-manifest',str(work/'build-manifest.json'),
    '--extra-cmdline',cmd[len(prefix):],'--output','out/boot-runtime68h','--image-name','boot-tb378fc-runtime68h.img'],check=True)
record={'status':'PRIVATE_RAM_BOOT_CANDIDATE_READY_NOT_SELECTED_OR_BOOTED',
        'private_settings_sha256':sha(target),'base_settings_sha256':manifest['settings_sha256'],
        'private_user_state_sha256':sha(private/'user-state68.tar.gz'),
        'boot_sha256':sha('out/boot-runtime68h/boot-tb378fc-runtime68h.img'),
        'pairing_and_wifi_preserved':True,'light_sensor_out_of_scope':True,
        'scope':'RAM-only. Existing running system and relay unchanged; no storage mounts or flashes.'}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
