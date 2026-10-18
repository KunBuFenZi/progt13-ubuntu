#!/usr/bin/env python3
"""Build ext4/JBD2 in a fresh small SDK without rebuilding or changing Image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume', action='store_true')
args = parser.parse_args()
kernel = root / 'kernel'
base = root / 'out/kernel-usbc70b'
sdk = root / 'out/kernel-ext4-78'
src = root / 'out/ext4-source78'
out = root / 'out/ext4-modules78'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
baseline = sha(base/'arch/arm64/boot/Image')
assert baseline == '21c91b2dddf71e38ed6ae4366135a56ec9e02fe9d617bba33937b3e40c6483e9'
if not args.resume:
    for p in [sdk, src, out]:
        p.mkdir(exist_ok=False)
    shutil.copy2(base/'.config', sdk/'.config')
    for name in ['ext4', 'jbd2']:
        shutil.copytree(kernel/'fs'/name, src/name)
    cache = src/'mbcache'; cache.mkdir()
    shutil.copy2(kernel/'fs/mbcache.c',cache/'mbcache.c')
    (cache/'Makefile').write_text('obj-m += mbcache.o\n')
else:
    assert sdk.is_dir() and src.is_dir() and not (out/'manifest.json').exists()
cache = src/'mbcache'
crc = src/'crc16'; crc.mkdir(exist_ok=True)
shutil.copy2(kernel/'lib/crc/crc16.c',crc/'crc16.c')
(crc/'Makefile').write_text('obj-m += crc16.o\n')
cfg=[str(kernel/'scripts/config'),'--file',str(sdk/'.config')]
subprocess.run(cfg+['--module','EXT4_FS'],check=True)
subprocess.run(cfg+['--enable','EXT4_FS_POSIX_ACL','--enable','EXT4_FS_SECURITY'],check=True)
subprocess.run(cfg+['--disable','EXT4_DEBUG','--disable','EXT4_KUNIT_TESTS'],check=True)
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
make=['make','-C',str(kernel),'O='+str(sdk),'LOCALVERSION=+','-j2']
subprocess.run(make+['olddefconfig'],env=env,check=True)
subprocess.run(make+['modules_prepare'],env=env,check=True)
shutil.copy2(base/'vmlinux.symvers',sdk/'Module.symvers')
symbols=[]
for directory in [crc,cache,src/'jbd2',src/'ext4']:
    command=make+['M='+str(directory),'modules']
    if symbols: command+=['KBUILD_EXTRA_SYMBOLS='+' '.join(map(str,symbols))]
    subprocess.run(command,env=env,check=True)
    symbols.append(directory/'Module.symvers')
modules={}
for p in src.rglob('*.ko'):
    imports={l.split()[-1] for l in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(p)],text=True).splitlines()}
    exports={l.split()[-1].removeprefix('__ksymtab_') for l in subprocess.check_output(['aarch64-linux-gnu-nm',str(p)],text=True).splitlines() if l.split() and l.split()[-1].startswith('__ksymtab_')}
    vermagic=subprocess.check_output(['modinfo','-F','vermagic',str(p)],text=True).strip()
    assert vermagic=='7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
    modules[p.name]={'sha256':sha(p),'imports':sorted(imports),'exports':sorted(exports),'vermagic':vermagic}
    shutil.copy2(p,out/p.name)
assert set(modules)=={'crc16.ko','mbcache.ko','jbd2.ko','ext4.ko'}
available={l.split()[1] for l in (base/'vmlinux.symvers').read_text().splitlines()}
order=[];pending=dict(modules)
while pending:
    ready=sorted(n for n,v in pending.items() if not set(v['imports'])-available)
    assert ready,{n:sorted(set(v['imports'])-available) for n,v in pending.items()}
    for n in ready:
        available.update(pending.pop(n)['exports']);order.append(n)
assert sha(base/'arch/arm64/boot/Image')==baseline
old={l.split('=',1)[0]:l.split('=',1)[1] for l in (base/'.config').read_text().splitlines() if '=' in l}
new={l.split('=',1)[0]:l.split('=',1)[1] for l in (sdk/'.config').read_text().splitlines() if '=' in l}
record={'status':'BUILT_NOT_LOADED','modules':modules,'order':order,
        'baseline_image_preserved':True,'config_changes':{k:[old.get(k),new.get(k)] for k in old.keys()|new.keys() if old.get(k)!=new.get(k)}}
(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='modules'},indent=2))
