#!/usr/bin/env python3
"""Package early UFS/ext4 support, a RAM setup boot, and persistent v4 boot."""
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

root=Path(__file__).resolve().parent.parent;os.chdir(root)
work=root/'out/runtime-persistent79';work.mkdir(exist_ok=False)
private=root/'out/private79';private.mkdir(mode=0o700,exist_ok=False)
early=root/'out/early-root79';early.mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
root_manifest=root/'out/persistent-root79/manifest.json'
rm=json.loads(root_manifest.read_text())
assert rm['status']=='OFFLINE_ROOT_CONTAINER_BUILT_NOT_DEVICE_BOOTED'
settings=root/'out/private77b/settings-ufs77b.tar'
assert sha(settings)=='fea01315e4a9a68ba0f8d20ce46f059225b17cc5b117daa7a270f84bab670c88'
entries={}
with tarfile.open(settings) as t:
    for m in t:entries[m.name]=(copy.copy(m),t.extractfile(m).read() if m.isfile() else None)
removed=[]
for n in ['etc/systemd/system/graphical.target.wants/tb378fc-ufs77.service',
          'etc/systemd/system/tb378fc-ufs77.service','usr/local/libexec/tb378fc-ufs77.py']:
    assert n in entries;entries.pop(n);removed.append(n)
n='etc/udev/rules.d/05-tb378fc-ufs77.rules'
data=b'SUBSYSTEM=="block", KERNELS=="1d84000.ufs", ENV{UDISKS_IGNORE}="1"\n'
m=copy.copy(entries[n][0]);m.size=len(data);entries[n]=(m,data)
setup_settings=private/'settings-setup79.tar'
with setup_settings.open('xb') as f:
    setup_settings.chmod(0o600)
    with tarfile.open(fileobj=f,mode='w') as t:
        for n,(m,b) in sorted(entries.items()):t.addfile(m,io.BytesIO(b) if b is not None else None)

files={}
def add(n,data,mode=0o644):
    p=early/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    files[n]={'sha256':sha(p),'mode':mode}

order=[]
for source in ['out/ext4-modules78','out/ufs-write79']:
    directory=root/source;manifest=json.loads((directory/'manifest.json').read_text())
    for n in manifest['order']:
        p=directory/n;assert sha(p)==manifest['modules'][n]['sha256']
        add('lib/modules/'+n,p.read_bytes());order.append(n)
overlay=root/'out/ufs77b-overlay-build';om=json.loads((overlay/'manifest.json').read_text())
assert sha(overlay/'live-ufs-overlay77.ko')==om['module_sha256']
assert sha(overlay/'tb378fc-ufs77.dtbo')==om['overlay_sha256']
add('lib/modules/live-ufs-overlay77.ko',(overlay/'live-ufs-overlay77.ko').read_bytes());order.append('live-ufs-overlay77.ko')
add('lib/firmware/tb378fc-ufs77.dtbo',(overlay/'tb378fc-ufs77.dtbo').read_bytes())
add('etc/early-modules',('\n'.join(order)+'\n').encode())
add('etc/root-uuid',(rm['uuid']+'\n').encode())
desktop=(root/'port/desktop-init').read_text()
marker='mkdir -p /run/evidence /run/desktop\n'
assert desktop.count(marker)==1 and desktop.count('@SETTINGS_SHA@')==1
desktop='#!/bin/sh\nexport PATH=/bin\n'+marker+desktop.split(marker,1)[1]
add('bin/desktop-init79',desktop.replace('@SETTINGS_SHA@',sha(setup_settings)).encode(),0o755)
reboot=work/'reboot-bootloader'
subprocess.run(['aarch64-linux-gnu-gcc','-static','-Os','-s','-o',str(reboot),str(root/'port/reboot-bootloader79.c')],check=True)
add('bin/reboot-bootloader',reboot.read_bytes(),0o755)
(early/'manifest.json').write_text(json.dumps({'files':files,'module_order':order,'root_uuid':rm['uuid']},indent=2)+'\n')
subprocess.run([sys.executable,'port/build-initramfs.py','--output','out/initramfs-persistent79',
    '--init-script','port/persistent-init79','--runtime-dir',str(early),
    '--extra-applets','wget sha256sum tar chown switch_root tee seq kill umount cp mv insmod findfs',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin','--gpu-firmware-dir','diagnostics/firmware/gpu',
    '--wifi-firmware-dir','out/wifi-native-v2','--adsp-firmware-dir','diagnostics/firmware/adsp'],check=True)
build=json.loads((root/'out/runtime-ufs77b/build-manifest.json').read_text())
build.update(status='PERSISTENT79_EARLY_UFS_EXT4_INTEGRATED',settings_sha256=sha(setup_settings))
(work/'build-manifest.json').write_text(json.dumps(build,indent=2)+'\n')
old=json.loads((root/'out/boot-ufs77b/manifest.json').read_text())
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert old['cmdline'].startswith(prefix)
subprocess.run([sys.executable,'port/package-stage1.py','--kernel','out/kernel-usbc70b/arch/arm64/boot/Image',
    '--dtb','out/recovery-tree75b/abl-static/erhai-abl.dtb',
    '--mainline-dtb','out/recovery-tree75b/sm8750-lenovo-tb378fc-recovery75.dtb',
    '--ramdisk','out/initramfs-persistent79/initramfs.cpio.gz','--build-manifest',str(work/'build-manifest.json'),
    '--extra-cmdline',old['cmdline'][len(prefix):]+' tb378fc.setup=1',
    '--output','out/boot-setup79','--image-name','boot-tb378fc-setup79.img'],check=True)
subprocess.run([sys.executable,'port/package-gki78.py','--output','out/gki-persistent79',
    '--ramdisk','out/initramfs-persistent79/initramfs.cpio.gz',
    '--existing-key','out/private78/tb378fc-trial-rsa4096.pem','--root-manifest',str(root_manifest)],check=True)
record={'status':'BUILT_NOT_DEVICE_TESTED','root_manifest':str(root_manifest.relative_to(root)),
    'ram_setup_boot':'out/boot-setup79/boot-tb378fc-setup79.img','persistent_triplet':'out/gki-persistent79',
    'setup_settings_sha256':sha(setup_settings),'root_uuid':rm['uuid'],
    'build_id':(root/'out/initramfs-persistent79/build-id').read_text().strip(),'early_module_order':order,
    'removed_setup_services':removed,'tablet_storage_written':False,
    'known_remaining':['Early UFS/ext4 device boot trial','Persistent-root device boot and reboot preservation',
        'Partition and Android-data decision before installation','Bootloader acceptance of signed v4 triplet']}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
