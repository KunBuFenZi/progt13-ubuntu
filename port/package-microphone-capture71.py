#!/usr/bin/env python3
"""Package the additive capture-card overlay and an extended AudioReach topology."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='out/microphone-capture71')
args=parser.parse_args()
work=(root/args.output).resolve()
assert work.is_relative_to(root/'out')
sdk=root/'out/kernel-usbc70b'
kernel=root/'kernel'
manifest=json.loads((work/'manifest.json').read_text())
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert all(sha(work/name)==value for name,value in manifest['files'].items())
config=(work/'Lenovo-TB378FC.conf').read_text()
baseline=(root/'out/topology-tb378fc/Lenovo-TB378FC.conf').read_text()
assert config.startswith(baseline), 'Existing playback topology must remain identical'
shutil.copy2(root/'port/live-microphone-capture71.c',work/'live-microphone-capture71.c')
(work/'Makefile').write_text('obj-m += live-microphone-capture71.o\n')
(sdk/'Module.symvers').write_bytes((sdk/'vmlinux.symvers').read_bytes())
subprocess.run(['make','-C',str(kernel),'O='+str(sdk),'LOCALVERSION=+',
                '-j2','M='+str(work),'modules'],check=True,
               env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-'))
module=work/'live-microphone-capture71.ko'
manifest['files'][module.name]=sha(module)
manifest['vermagic']=subprocess.check_output(['modinfo','-F','vermagic',str(module)],text=True).strip()
manifest['imports']=[line.split()[-1] for line in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(module)],text=True).splitlines()]
(work/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open(work/'runtime.tar','w') as tar:
    for name in ['manifest.json',module.name,'tb378fc-microphone-capture71.dtbo','Lenovo-TB378FC-tplg.bin']:
        tar.add(work/name,arcname=name)
print(json.dumps({'status':'CAPTURE_CARD_READY_NOT_LOADED','tar_sha256':sha(work/'runtime.tar')}))
