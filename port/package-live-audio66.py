#!/usr/bin/env python3
"""Modular GPIO-audio desktop, with one staged runtime setup after actual display confirmation."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
def run(*args): subprocess.run([str(a) for a in args],check=True)
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
m=json.loads(Path('out/live-audio-kernel66-build.json').read_text())
for name,info in m['files'].items(): assert digest(name)==info['sha256'],name
run(sys.executable,'port/prepare-live-audio-tree66.py')
source=Path('port/sm8750-lenovo-tb378fc-audio-gpio.dts')
dest=Path('kernel/arch/arm64/boot/dts/qcom')/source.name
dest.write_bytes(source.read_bytes())
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
subprocess.run(['make','-C','kernel','O='+str(ROOT/'out/kernel-memory'),'LOCALVERSION=+',
                'qcom/sm8750-lenovo-tb378fc-audio-gpio.dtb'],env=env,check=True)
tree=Path('out/live-audio-tree66');tree.mkdir(exist_ok=False)
dtb=tree/'sm8750-lenovo-tb378fc-audio-gpio.dtb'
dtb.write_bytes((ROOT/'out/kernel-memory/arch/arm64/boot/dts/qcom'/dtb.name).read_bytes())
run(sys.executable,'reference-tools/build-erhai-abl-symbols.py','--mainline-dtb',dtb,
    '--dtbo-img','inputs/dtbo.img','--base-dir','inputs/stock-base','--identity-index','11',
    '--dtc','out/kernel-memory/scripts/dtc/dtc','--output',tree/'abl')

# Extend the reviewed baseline overlay; do not regenerate unrelated desktop policy.
baseline=Path('out/checkpoint-battery-desktop-good/settings.tar')
assert digest(baseline)=='72aa8ad1a4d55bc3f4b8cfe20f5aaeab6b7d4cfc7794865d9f266880569c9bfb'
overlay=Path('out/live-audio-settings66.tar')
additions={
 'usr/lib/firmware/awinic/tb378fc/aw88480-native-music.acf':(Path('out/audio-native/aw88480-native-music.acf'),0o644),
 'usr/lib/firmware/qcom/sm8750/Lenovo-TB378FC-tplg.bin':(Path('out/topology-tb378fc/Lenovo-TB378FC-tplg.bin'),0o644),
 'usr/share/alsa/ucm2/Qualcomm/sm8750/Lenovo-TB378FC/Lenovo-TB378FC.conf':(Path('port/audio/Lenovo-TB378FC.conf'),0o644),
 'usr/share/alsa/ucm2/Qualcomm/sm8750/Lenovo-TB378FC/HiFi.conf':(Path('port/audio/HiFi.conf'),0o644),
}
with tarfile.open(baseline) as old,tarfile.open(overlay,'w') as new:
 for member in old.getmembers():
  if member.name=='etc/systemd/system/tb378fc-ram-expiry.timer':
   data=old.extractfile(member).read().replace(b'45min',b'2h').replace(b'45 minutes',b'2 hours')
   member.size=len(data);new.addfile(member,io.BytesIO(data))
  else: new.addfile(member,old.extractfile(member) if member.isfile() else None)
 existing={a.name for a in old.getmembers()}
 for name,(path,mode) in additions.items():
  for parent in reversed(Path(name).parents):
   if str(parent)!='.' and str(parent) not in existing:
    info=tarfile.TarInfo(str(parent));info.type=tarfile.DIRTYPE;info.mode=0o755
    new.addfile(info);existing.add(str(parent))
  data=path.read_bytes();info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode
  new.addfile(info,io.BytesIO(data))
 name='usr/share/alsa/ucm2/conf.d/sm8750/Lenovo-TB378FC.conf'
 for parent in reversed(Path(name).parents):
  if str(parent)!='.' and str(parent) not in existing:
   info=tarfile.TarInfo(str(parent));info.type=tarfile.DIRTYPE;info.mode=0o755
   new.addfile(info);existing.add(str(parent))
 info=tarfile.TarInfo(name);info.type=tarfile.SYMTYPE;info.mode=0o777
 info.linkname='../../Qualcomm/sm8750/Lenovo-TB378FC/Lenovo-TB378FC.conf'
 new.addfile(info)
settings_hash=digest(overlay)

init=Path('out/live-audio66-init')
script=Path('port/desktop-init').read_text()
assert script.count('@SETTINGS_SHA@')==1
script=script.replace('@SETTINGS_SHA@',settings_hash)
script+='# Modular-audio66 kernel sha256 '+digest('out/kernel-live-audio66/arch/arm64/boot/Image')+'\n'
# CPUCP/SCMI are built in, matching the previously verified eight-core path.
init.write_text(script)
run(sys.executable,'port/build-initramfs.py','--output','out/initramfs-live-audio66',
    '--init-script',init,'--extra-applets','wget sha256sum tar chown switch_root tee seq kill umount cp mv',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu','--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp')
for name in [str(source),str(dtb),'port/package-live-audio66.py',str(init),str(overlay)]:
 m['files'][name]={'sha256':digest(name),'size':Path(name).stat().st_size}
m['settings_sha256']=settings_hash
m['status']='MODULAR_GPIO_AUDIO_RAM_DESKTOP_NOT_DEVICE_TESTED'
build=Path('out/live-audio66-build.json');build.write_text(json.dumps(m,indent=2)+'\n')
original=json.loads(Path('out/boot-battery-desktop-v8/manifest.json').read_text())['cmdline']
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert original.startswith(prefix)
extra=original[len(prefix):].replace('nr_cpus=7','nr_cpus=8')
run(sys.executable,'port/package-stage1.py','--kernel','out/kernel-live-audio66/arch/arm64/boot/Image',
    '--dtb',tree/'abl/erhai-abl.dtb','--mainline-dtb',dtb,
    '--ramdisk','out/initramfs-live-audio66/initramfs.cpio.gz','--build-manifest',build,
    '--extra-cmdline',extra,'--output','out/boot-live-audio66','--image-name','boot-tb378fc-live-audio66.img')
print('Offline package complete; select settings only immediately before this candidate boot')
