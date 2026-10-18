#!/usr/bin/env python3
"""Combine the checked kernel, native DT and accepted runtime for one RAM boot."""
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
assert sha('out/peripherals-runtime67.tar.gz')=='c57d3ec3e892243cb44ea4e83bccf829226a2ffb63fb4b91ec8efcccf7d1c70e'
assert sha('out/accepted-desktop-config68.tar.gz')=='264cecbd0e51720cfb723c1a9f5e85de6c86c76cffe946e6c157617d40a8a1e5'
assert sha('out/live-audio-settings66.tar')=='6c7b102d9027c1ca025eca6f5e093d49053bb9afc0731eb235ec72b51d620d28'
image=Path('out/kernel-peripherals68/arch/arm64/boot/Image')
assert sha(image)=='f19fe3e8ac5cfdbc02a8252dc9c9277f0ef42e2be1bbcc9b1099079358da8302'
sdk=Path('out/kernel-peripherals68')
dt=Path('out/peripherals-tree68/sm8750-lenovo-tb378fc-peripherals.dtb')
assert sha(dt)==json.loads(dt.with_name('tree-manifest.json').read_text())['dtb_sha256']
out=Path('out/peripherals-package68d');out.mkdir(exist_ok=False)
entries={}
def read_tar(path):
    with tarfile.open(path) as t:
        for m in t:
            assert not m.name.startswith('/') and '..' not in Path(m.name).parts
            if m.name.startswith('run/') or m.name.endswith('-manifest.json') or m.name.endswith('manifest.json'):continue
            entries[m.name]=(copy.copy(m),t.extractfile(m).read() if m.isfile() else None)
def add(name,data,mode=0o644):
    if isinstance(data,str):data=data.encode()
    m=tarfile.TarInfo(name);m.mode=mode;m.size=len(data);entries[name]=(m,data)
def file(name,path,mode=0o644):add(name,Path(path).read_bytes(),mode)
def link(name,target):
    m=tarfile.TarInfo(name);m.mode=0o777;m.type=tarfile.SYMTYPE;m.linkname=target;entries[name]=(m,None)
read_tar('out/live-audio-settings66.tar')
read_tar('out/peripherals-runtime67.tar.gz')
read_tar('out/accepted-desktop-config68.tar.gz')
# Never ship the prior kernel's diagnostic modules.
assert not any(n.endswith('.ko') for n in entries)
kernel_release=(sdk/'include/config/kernel.release').read_text().strip()
modules=Path('out/runtime-modules68')
manifest=json.loads((modules/'manifest.json').read_text())
assert len(manifest)==56
module_path='usr/lib/modules/'+kernel_release
exports={l.split()[1] for l in (sdk/'vmlinux.symvers').read_text().splitlines()}
for info in manifest.values():exports.update(info['exports'])
for name,info in manifest.items():
    assert sha(modules/name)==info['sha256']
    assert not set(info['undefined'])-exports
    file(module_path+'/extra/'+name,modules/name)
for name in ('modules.builtin','modules.builtin.modinfo'):file(module_path+'/'+name,sdk/name)
file('usr/share/tb378fc/runtime-modules68.json',modules/'manifest.json')
video=Path('out/native-vendor67-files/firmware/vpu35_4v.mbn')
assert sha(video)=='523468f5bc86d740a22bccdcabf7365747b8f4ddce3fdc642a41e1ca9263debc'
file('usr/lib/firmware/qcom/sm8750/tb378fc/vpu35_4v.mbn',video)
with tarfile.open('out/native-bluetooth68.tar.gz') as t:
    bt=json.load(t.extractfile('manifest.json'))
    assert bt['status']=='ALL_65_USED_FILES_MATCH_FAT_CHAINS'
    for name,info in bt['files'].items():
        content=t.extractfile(name).read()
        assert hashlib.sha256(content).hexdigest()==info['sha256']
        # Names stay native until the real controller's ROM and board ID are read.
        add('usr/lib/firmware/qca/tb378fc/'+Path(name).name,content)
file('etc/udev/rules.d/81-tb378fc-sensors-staging.rules','port/sensors/81-tb378fc-sensors-accel-gyro.rules')
add('etc/sysusers.d/tb378fc-sensors.conf','g fastrpc -\nu fastrpc -:fastrpc "Sensor RPC" /nonexistent /usr/sbin/nologin\n')
file('usr/local/libexec/tb378fc-runtime68','port/tb378fc-runtime68',0o755)
file('etc/systemd/system/tb378fc-runtime68.service','port/tb378fc-runtime68.service')
add('etc/systemd/system/tb378fc-sensors-rpcd.service.d/91-runtime-order.conf',
    '[Unit]\nRequires=tb378fc-runtime68.service\nAfter=tb378fc-runtime68.service\n')
file('usr/local/bin/tb378fc-desktop68','port/tb378fc-desktop68',0o755)
add('etc/xdg/autostart/tb378fc-desktop68.desktop',
    '[Desktop Entry]\nType=Application\nName=Tablet desktop runtime\nExec=/usr/local/bin/tb378fc-desktop68\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n')
add('etc/tb378fc-candidate','peripherals68\n')
add('etc/tmpfiles.d/tb378fc-touch.conf','f /run/tb378fc-touch-dispatch.json 0644 root root - {"pickFallback":false,"trace":false}\n')
add('etc/modprobe.d/tb378fc-staged68.conf',
    '# Keep DSP/audio and new untested engines deferred until explicit activation.\n'+
    ''.join('blacklist '+n+'\n' for n in ('snd_soc_sc8280xp','snd_soc_aw88480','i2c_gpio','apr','fastrpc','qcom_iris','hci_uart','videocc_sm8750')))
link('etc/systemd/system/graphical.target.wants/tb378fc-runtime68.service','../tb378fc-runtime68.service')
link('etc/systemd/system/graphical.target.wants/iio-sensor-proxy.service','/usr/lib/systemd/system/iio-sensor-proxy.service')
link('etc/systemd/system/graphical.target.wants/tb378fc-power-key.service','../tb378fc-power-key.service')
# A fresh real-time clock seed avoids the previous twelve-hour skew.
epoch=int(__import__('time').time())
name='usr/lib/clock-epoch'
if name in entries:add(name,str(epoch)+'\n')
stage=out/'module-root'
(stage/module_path/'extra').mkdir(parents=True)
(stage/'lib').symlink_to('usr/lib',target_is_directory=True)
for name in [n for n in entries if n.startswith(module_path+'/')]:
    p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(entries[name][1])
subprocess.run(['depmod','-b',str(stage),'-F',str(sdk/'System.map'),kernel_release],check=True)
for p in (stage/module_path).glob('modules.*'):
    if p.name not in ('modules.builtin','modules.builtin.modinfo'):file(module_path+'/'+p.name,p)
# Sensor data is private to this tablet. Directory ownership is set by runtime.
for name,(m,data) in entries.items():
    if name.startswith('usr/share/tb378fc/sensors/') and m.isfile():m.mode=0o640
target=out/'settings.tar'
with tarfile.open(target,'w') as t:
    directories=set()
    for name,(m,data) in sorted(entries.items()):
        if name=='.':continue
        for parent in reversed(Path(name).parents):
            rel=parent.as_posix()
            if rel=='.' or rel in directories or rel in entries:continue
            d=tarfile.TarInfo(rel);d.type=tarfile.DIRTYPE;d.mode=0o755;t.addfile(d);directories.add(rel)
        t.addfile(m,io.BytesIO(data) if data is not None else None)
    check={n:hashlib.sha256(d).hexdigest() for n,(m,d) in entries.items() if d is not None}
(out/'files-sha256.json').write_text(json.dumps(check,indent=2)+'\n')
init=out/'init'
script=Path('port/desktop-init').read_text()
assert script.count('@SETTINGS_SHA@')==1
init.write_text(script.replace('@SETTINGS_SHA@',sha(target)))
subprocess.run([sys.executable,'port/build-initramfs.py','--output','out/initramfs-peripherals68','--init-script',str(init),
    '--extra-applets','wget sha256sum tar chown switch_root tee seq kill umount cp mv',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin','--gpu-firmware-dir','diagnostics/firmware/gpu',
    '--wifi-firmware-dir','out/wifi-native-v2','--adsp-firmware-dir','diagnostics/firmware/adsp'],check=True)
subprocess.run([sys.executable,'reference-tools/build-erhai-abl-symbols.py','--mainline-dtb',str(dt),
    '--dtbo-img','inputs/dtbo.img','--base-dir','inputs/stock-base','--identity-index','11',
    '--dtc',str(sdk/'scripts/dtc/dtc'),'--output','out/peripherals-tree68/abl'],check=True)
build=json.loads(Path('out/native-touch67-build.json').read_text())
build.update(status='PERIPHERALS68_OFFLINE_ONLY_NOT_DEVICE_TESTED',settings_sha256=sha(target))
for p in [image,dt,target,init]:build['files'][p.as_posix()]={'sha256':sha(p),'size':p.stat().st_size}
record=out/'build-manifest.json';record.write_text(json.dumps(build,indent=2)+'\n')
cmd=json.loads(Path('out/boot-native-touch67/manifest.json').read_text())['cmdline']
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert cmd.startswith(prefix)
subprocess.run([sys.executable,'port/package-stage1.py','--kernel',str(image),'--dtb','out/peripherals-tree68/abl/erhai-abl.dtb',
    '--mainline-dtb',str(dt),'--ramdisk','out/initramfs-peripherals68/initramfs.cpio.gz','--build-manifest',str(record),
    '--extra-cmdline',cmd[len(prefix):],'--output','out/boot-peripherals68','--image-name','boot-tb378fc-peripherals68.img'],check=True)
print('OFFLINE_CANDIDATE_READY_NO_RELAY_CHANGED',sha(target),flush=True)
