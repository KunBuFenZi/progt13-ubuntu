#!/usr/bin/env python3
"""Compare one frozen kernel/tree input with the failed display candidate."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
os.chdir(root)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('variant',choices=['battery-tree','battery-kernel','sound-disabled','amps-disabled'])
args=p.parse_args()
suffix='display-'+args.variant
kernel='out/kernel-cpu-audio-ready/arch/arm64/boot/Image'
dtb='out/abl-audio-gated/erhai-abl.dtb'
mainline='out/kernel-audio-gated/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio.dtb'
if args.variant=='battery-tree':
    dtb='out/battery-probe-v3/abl/erhai-abl.dtb'
    mainline='out/battery-probe-v3/sm8750-lenovo-tb378fc-battery.dtb'
elif args.variant=='battery-kernel':
    kernel='out/kernel-battery-v2/arch/arm64/boot/Image'
m=json.loads(Path('out/cpu-display-probe-build.json').read_text())
for name in [kernel,mainline]:
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==m['files'][name]['sha256']
if args.variant in ['sound-disabled','amps-disabled']:
    directory=Path('out/display-'+args.variant+'-tree')
    directory.mkdir(exist_ok=False)
    copy=directory/'sm8750-lenovo-tb378fc-audio.dtb'
    shutil.copyfile(mainline,copy)
    subprocess.run(['fdtput','-t','s',str(copy),'/sound','status','disabled'],check=True)
    if args.variant=='amps-disabled':
        for address in ['34','35','36','37']:
            subprocess.run(['fdtput','-t','s',str(copy),
                '/soc@0/geniqup@ac0000/i2c@a94000/amplifier@'+address,
                'status','disabled'],check=True)
    subprocess.run([sys.executable,'reference-tools/build-erhai-abl-symbols.py',
        '--mainline-dtb',str(copy),'--dtbo-img','inputs/dtbo.img',
        '--base-dir','inputs/stock-base','--identity-index','11',
        '--dtc','out/kernel-memory/scripts/dtc/dtc','--output',str(directory/'abl')],check=True)
    mainline=str(copy)
    dtb=str(directory/'abl/erhai-abl.dtb')
    m['files'][mainline]={'sha256':hashlib.sha256(copy.read_bytes()).hexdigest(),'size':copy.stat().st_size}
init=Path('out/'+suffix+'-init')
init.write_text(Path('port/cpu-display-probe-init').read_text()+'\n# Comparison: '+args.variant+'\n')
for name in ['port/package-display-isolation.py',str(init)]:
    path=Path(name)
    m['files'][name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':path.stat().st_size}
m['status']='DISPLAY_ONE_INPUT_ISOLATION_NOT_TESTED'
build=Path('out/'+suffix+'-build.json')
build.write_text(json.dumps(m,indent=2)+'\n')
def run(*args): subprocess.run([str(a) for a in args],check=True)
ram='out/initramfs-'+suffix
run(sys.executable,'port/build-initramfs.py','--output',ram,
    '--init-script',init,'--kms-test','out/kms-test',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu','--wifi-firmware-dir','out/wifi-native-v2',
    '--adsp-firmware-dir','diagnostics/firmware/adsp',
    '--amp-firmware','out/audio-native/aw88480-native-music.acf',
    '--audio-runtime-dir','out/audio-runtime',
    '--audio-topology','out/topology-tb378fc/Lenovo-TB378FC-tplg.bin')
baseline=json.loads(Path('out/boot-cpu-display-probe/manifest.json').read_text())
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert baseline['cmdline'].startswith(prefix+' ')
run(sys.executable,'port/package-stage1.py','--kernel',kernel,'--dtb',dtb,
    '--mainline-dtb',mainline,'--ramdisk',ram+'/initramfs.cpio.gz',
    '--build-manifest',build,'--extra-cmdline',baseline['cmdline'][len(prefix)+1:],
    '--output','out/boot-'+suffix,'--image-name','boot-tb378fc-'+suffix+'.img')
