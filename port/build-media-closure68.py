#!/usr/bin/env python3
"""Build mutually dependent V4L2/vb2/Iris modules in one modpost invocation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
source=root/'kernel/drivers/media'
dest=root/'out/media-closure68b'
assert not dest.exists()
dest.mkdir()
paths={'v4l2':'v4l2-core','vb2':'common/videobuf2','iris':'platform/qcom/iris'}
originals={}
for short,long in paths.items():
    out=dest/short;out.mkdir()
    for p in (source/long).iterdir():
        if p.is_file() and (p.suffix in ('.c','.h') or p.name=='Makefile'):
            shutil.copy2(p,out/p.name)
            originals[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
    make=out/'Makefile'
    text=make.read_text()
    if short=='v4l2':
        # Do not bring the unrelated tuner helper into this dependency closure.
        text=text.replace('obj-$(CONFIG_VIDEO_TUNER) += tuner.o','')
    make.write_text(text)
(dest/'Makefile').write_text('obj-m += v4l2/ vb2/ iris/\n')
sdk=root/'out/kernel-peripherals68'
assert 'CONFIG_MEDIA_CONTROLLER=y\n' in (sdk/'.config').read_text()
assert '\tmedia_device_init\t' in (sdk/'vmlinux.symvers').read_text()
shutil.copy2(sdk/'vmlinux.symvers',sdk/'Module.symvers')
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
subprocess.run(['make','-C',str(root/'kernel'),'O='+str(sdk),'LOCALVERSION=+','-j3','M='+str(dest),'modules'],env=env,check=True)
manifest={}
exports={line.split()[1] for line in (sdk/'vmlinux.symvers').read_text().splitlines()}
for p in dest.rglob('*.ko'):
    names=subprocess.check_output(['aarch64-linux-gnu-nm',str(p)],text=True)
    undefined=subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(p)],text=True)
    record={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'vermagic':subprocess.check_output(['modinfo','-F','vermagic',str(p)],text=True).strip(),
            'exports':[s.split()[-1].removeprefix('__ksymtab_') for s in names.splitlines() if s.split() and s.split()[-1].startswith('__ksymtab_')],
            'undefined':[s.split()[-1] for s in undefined.splitlines() if s.split()]}
    manifest[str(p.relative_to(dest))]=record;exports.update(record['exports'])
missing={n:sorted(set(i['undefined'])-exports) for n,i in manifest.items() if set(i['undefined'])-exports}
assert not missing,missing
(dest/'manifest.json').write_text(json.dumps({'status':'OFFLINE_ONLY','source_files_sha256':originals,'modules':manifest},indent=2)+'\n')
print('VERIFIED_MODULE_CLOSURE',len(manifest),flush=True)
