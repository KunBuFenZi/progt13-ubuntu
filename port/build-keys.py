#!/usr/bin/env python3
"""Build and package verified key wiring with the already-built Wi-Fi kernel."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(*args,**kwargs):subprocess.run([str(a) for a in args],check=True,**kwargs)
wifi=json.loads(Path('out/wifi-build.json').read_text())
image='out/kernel-wifi/arch/arm64/boot/Image'
assert sha(image)==wifi['files'][image]['sha256']
run(sys.executable,'port/prepare-keys.py')
src='port/sm8750-lenovo-tb378fc-keys.dts'
shutil.copy2(src,'kernel/arch/arm64/boot/dts/qcom/')
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
run('make','-C','kernel','O='+str(ROOT/'out/kernel-wifi'),
    'qcom/sm8750-lenovo-tb378fc-keys.dtb',env=env)
dtb='out/kernel-wifi/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-keys.dtb'
inputs=[image,dtb,'out/kernel-wifi/.config','port/prepare-keys.py',
        'port/build-keys.py','diagnostics/live-device-tree.json']
inputs += [str(p) for p in sorted(Path('port').glob('sm8750-lenovo-tb378fc*.dts'))]
manifest={'status':'OFFLINE_KEYS_AND_WIFI_CANDIDATE_NOT_DEVICE_TESTED',
 'kernel_commit':wifi['kernel_commit'],
 'files':{name:{'sha256':sha(name),'size':Path(name).stat().st_size} for name in inputs}}
Path('out/keys-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert not Path('out/abl-wifi-keys').exists()
run(sys.executable,'reference-tools/build-erhai-abl-symbols.py',
    '--mainline-dtb',dtb,'--dtbo-img','inputs/dtbo.img',
    '--base-dir','inputs/stock-base','--identity-index','11',
    '--dtc','out/kernel-wifi/scripts/dtc/dtc','--output','out/abl-wifi-keys')
baseline=json.loads(Path('out/boot-desktop-awake/manifest.json').read_text())
base='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert baseline['cmdline'].startswith(base+' ')
run(sys.executable,'port/package-stage1.py','--kernel',image,
    '--dtb','out/abl-wifi-keys/erhai-abl.dtb','--mainline-dtb',dtb,
    '--ramdisk','out/initramfs-desktop-awake/initramfs.cpio.gz',
    '--build-manifest','out/keys-build.json','--extra-cmdline',baseline['cmdline'][len(base)+1:],
    '--output','out/boot-wifi-keys','--image-name','boot-tb378fc-wifi-keys-v2.img')
print('WIFI_KEYS_CANDIDATE_PACKAGED_NOT_YET_HARDWARE_TESTED')
