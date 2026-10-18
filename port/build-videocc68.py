#!/usr/bin/env python3
"""Build the missing video clock module for the already frozen candidate Image."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
sdk=root/'out/kernel-peripherals68'
assert hashlib.sha256((sdk/'arch/arm64/boot/Image').read_bytes()).hexdigest()=='f19fe3e8ac5cfdbc02a8252dc9c9277f0ef42e2be1bbcc9b1099079358da8302'
source=root/'kernel/drivers/clk/qcom'
work=root/'out/videocc-module68';work.mkdir(exist_ok=False)
for p in [source/'videocc-sm8750.c',*source.glob('*.h')]:
    shutil.copy2(p,work/p.name)
(work/'Makefile').write_text('obj-m += videocc-sm8750.o\n')
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
shutil.copy2(sdk/'vmlinux.symvers',sdk/'Module.symvers')
subprocess.run(['make','-C',str(root/'kernel'),'O='+str(sdk),'LOCALVERSION=+','-j3','M='+str(work),'modules'],env=env,check=True)
p=work/'videocc-sm8750.ko'
names=subprocess.check_output(['aarch64-linux-gnu-nm',str(p)],text=True)
info={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
      'vermagic':subprocess.check_output(['modinfo','-F','vermagic',str(p)],text=True).strip(),
      'exports':[s.split()[-1].removeprefix('__ksymtab_') for s in names.splitlines() if s.split() and s.split()[-1].startswith('__ksymtab_')],
      'undefined':[s.split()[-1] for s in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(p)],text=True).splitlines() if s.split()]}
available={line.split()[1] for line in (sdk/'vmlinux.symvers').read_text().splitlines()}
assert not set(info['undefined'])-available
dest=root/'out/runtime-modules68'
manifest=json.loads((dest/'manifest.json').read_text())
assert p.name not in manifest
shutil.copy2(p,dest/p.name);manifest[p.name]=info
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('VIDEO_CLOCK_MODULE_VERIFIED',len(manifest),info['sha256'],flush=True)
