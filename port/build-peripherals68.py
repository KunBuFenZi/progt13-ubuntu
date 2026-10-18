#!/usr/bin/env python3
"""Prepare a separate kernel with media/Bluetooth frameworks, leaving live67 intact."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
kernel=root/'kernel'
base=root/'out/kernel-memory'
work=root/'out/kernel-peripherals68'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(root/'out/kernel-live-audio66/arch/arm64/boot/Image')=='76d9c3d37db959d3453f2d75722751e0e046c879a600031420e6ec33d22213ce'
assert (base/'.config').read_bytes()==(root/'out/kernel-live-audio66/.config').read_bytes()
assert not work.exists(), 'Never reuse a different candidate identity'
subprocess.run(['cp','-a','--reflink=auto',str(base),str(work)],check=True)
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
config=kernel/'scripts/config'
enable=['MEDIA_SUPPORT','MEDIA_PLATFORM_SUPPORT','V4L2_MEM2MEM_DEV','BT_BREDR','BT_LE',
        'BT_HCIUART_SERDEV','BT_HCIUART_QCA','BT_RFCOMM_TTY']
modules=['VIDEO_DEV','MEDIA_CONTROLLER','VIDEO_QCOM_IRIS','BT','BT_HCIUART','BT_RFCOMM','BT_BNEP','BT_HIDP']
for option in enable:
    subprocess.run([str(config),'--file',str(work/'.config'),'-e',option],check=True)
for option in modules:
    subprocess.run([str(config),'--file',str(work/'.config'),'-m',option],check=True)
subprocess.run([str(config),'--file',str(work/'.config'),'-d','MEDIA_SUPPORT_FILTER'],check=True)
subprocess.run(['make','-C',str(kernel),'O='+str(work),'LOCALVERSION=+','olddefconfig'],env=env,check=True)
text=(work/'.config').read_text()
for symbol,value in [('MEDIA_SUPPORT','y'),('VIDEO_DEV','m'),('VIDEO_QCOM_IRIS','m'),('BT','m'),('BT_HCIUART_QCA','y')]:
    assert f'CONFIG_{symbol}={value}\n' in text, symbol
diff=subprocess.check_output(['git','-C',str(kernel),'diff','--binary'])
(work/'source-working-tree.patch').write_bytes(diff)
record={'status':'OFFLINE_CANDIDATE_NO_DEVICE_BOOT','base_image_sha256':'76d9c3d37db959d3453f2d75722751e0e046c879a600031420e6ec33d22213ce',
        'base_config_sha256':sha(base/'.config'),'candidate_config_sha256':sha(work/'.config'),
        'recipe_sha256':sha(__file__),'kernel_commit':subprocess.check_output(['git','-C',str(kernel),'rev-parse','HEAD'],text=True).strip(),
        'working_tree_patch_sha256':sha(work/'source-working-tree.patch'),
        'purpose':'Modules only preparation; video node and BT UART remain disabled until native firmware/DT is verified'}
(root/'out/peripherals68-input.json').write_text(json.dumps(record,indent=2)+'\n')
subprocess.run(['make','-C',str(kernel),'O='+str(work),'LOCALVERSION=+','-j3','Image'],env=env,check=True)
record.update(status='OFFLINE_IMAGE_ONLY_NOT_DEVICE_BOOTED',image_sha256=sha(work/'arch/arm64/boot/Image'))
(root/'out/peripherals68-image.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2),flush=True)
