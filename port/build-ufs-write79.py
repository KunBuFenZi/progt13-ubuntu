#!/usr/bin/env python3
"""Build normal UFS media drivers for the future dedicated Linux root.

Offline only. The running tablet keeps the separate read-only77 stack.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
kernel=root/'kernel'; sdk=root/'out/kernel-ufs77'; base=root/'out/kernel-usbc70b'
src=root/'out/ufs-write-source79'; out=root/'out/ufs-write79'
src.mkdir(exist_ok=False); out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
reference=json.loads((root/'out/ufs77-modules/manifest.json').read_text())
for n,h in reference['source_pins'].items():assert sha(kernel/n)==h
assert sha(base/'arch/arm64/boot/Image')=='21c91b2dddf71e38ed6ae4366135a56ec9e02fe9d617bba33937b3e40c6483e9'
for n in ['scsi','ufs']:shutil.copytree(kernel/'drivers'/n,src/n)
assert 'TB378FC_UFS77 forced read-only' not in (src/'scsi/sd.c').read_text()
assert 'tb378fc_ufs77_read_command' not in (src/'ufs/core/ufshcd.c').read_text()
p=src/'scsi/Makefile';t=p.read_text();old='include/scsi/scsi_devinfo.h FORCE';new='$(srctree)/include/scsi/scsi_devinfo.h FORCE'
if new not in t:
    assert t.count(old)==1;p.write_text(t.replace(old,new))
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
make=['make','-C',str(kernel),'O='+str(sdk),'LOCALVERSION=+','-j2']
symbols=[]
for directory in [src/'scsi',src/'ufs/core',src/'ufs/host']:
    cmd=make+['M='+str(directory),'modules']
    if symbols:cmd+=['KBUILD_EXTRA_SYMBOLS='+' '.join(map(str,symbols))]
    subprocess.run(cmd,env=env,check=True);symbols.append(directory/'Module.symvers')
modules={}
for p in src.rglob('*.ko'):
    if p.name not in reference['modules']:continue
    imports={l.split()[-1] for l in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(p)],text=True).splitlines()}
    exports={l.split()[-1].removeprefix('__ksymtab_') for l in subprocess.check_output(['aarch64-linux-gnu-nm',str(p)],text=True).splitlines() if l.split() and l.split()[-1].startswith('__ksymtab_')}
    v=subprocess.check_output(['modinfo','-F','vermagic',str(p)],text=True).strip()
    assert v=='7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
    modules[p.name]={'sha256':sha(p),'imports':sorted(imports),'exports':sorted(exports),'vermagic':v}
    shutil.copy2(p,out/p.name)
available={l.split()[1] for l in (base/'vmlinux.symvers').read_text().splitlines()}
pending=dict(modules);order=[]
while pending:
    ready=sorted(n for n,v in pending.items() if not set(v['imports'])-available)
    assert ready,{n:sorted(set(v['imports'])-available) for n,v in pending.items()}
    for n in ready:order.append(n);available.update(pending.pop(n)['exports'])
assert set(modules)==set(reference['modules'])
record={'status':'BUILT_NOT_LOADED','scope':'normal upstream SCSI/UFS drivers for future dedicated Linux root',
        'media_writes_supported':True,'modules':modules,'order':order,'source_pins':reference['source_pins'],
        'running_read_only_stack_changed':False,'no_rpmb_or_ufs_bsg':True}
(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='modules'},indent=2))
