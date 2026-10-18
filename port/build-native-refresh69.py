#!/usr/bin/env python3
"""Build a separate Image with the checked native panel timing candidate."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
work=root/'out/kernel-refresh69';assert not work.exists()
candidate=root/'out/native-refresh69b/panel-novatek-nt36526-refresh69.c'
manifest=json.loads(candidate.with_name('manifest.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(candidate)==manifest['candidate_source_sha256']
source=root/'kernel/drivers/gpu/drm/panel/panel-novatek-nt36526.c'
original=source.read_bytes();assert hashlib.sha256(original).hexdigest()==manifest['source_sha256']
subprocess.run(['cp','-a','--reflink=auto',str(root/'out/kernel-peripherals68'),str(work)],check=True)
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
try:
    source.write_bytes(candidate.read_bytes())
    subprocess.run(['make','-C',str(root/'kernel'),'O='+str(work),'LOCALVERSION=+','-j2','Image'],check=True,env=env)
finally:
    source.write_bytes(original)
assert source.read_bytes()==original
assert (work/'.config').read_bytes()==(root/'out/kernel-peripherals68/.config').read_bytes()
assert (work/'vmlinux.symvers').read_bytes()==(root/'out/kernel-peripherals68/vmlinux.symvers').read_bytes()
record={'status':'OFFLINE_KERNEL_BUILT_NOT_BOOTED',
        'image_sha256':sha(work/'arch/arm64/boot/Image'),
        'base_kernel_sha256':sha(root/'out/kernel-peripherals68/arch/arm64/boot/Image'),
        'config_identical':True,'exports_identical':True,'original_source_restored':True,
        'panel_candidate':manifest,'scope':'Only native 60/120/144Hz mode list; default120 unchanged; no live display rebind'}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='panel_candidate'},indent=2))
