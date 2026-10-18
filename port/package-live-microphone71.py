#!/usr/bin/env python3
"""Build the small OF loader and package the already-built additive modules."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

root = Path(__file__).resolve().parent.parent
work = root/'out/microphone-runtime71'
work.mkdir(exist_ok=False)
sdk = root/'out/kernel-usbc70b'
kernel = root/'kernel'
modules = json.loads((root/'out/live-microphone71/manifest.json').read_text())
foundation = json.loads((root/'out/microphone-foundation71/manifest.json').read_text())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert modules['base_kernel_image_sha256'] == sha(sdk/'arch/arm64/boot/Image')
assert foundation['base_sha256'] == sha(root/'out/usbc-tree70b/sm8750-lenovo-tb378fc-usbc70.dtb')
shutil.copy2(root/'port/live-microphone-overlay71.c',work/'live-microphone-overlay71.c')
(work/'Makefile').write_text('obj-m += live-microphone-overlay71.o\n')
(sdk/'Module.symvers').write_bytes((sdk/'vmlinux.symvers').read_bytes())
subprocess.run(['make','-C',str(kernel),'O='+str(sdk),'LOCALVERSION=+',
                '-j2','M='+str(work),'modules'],check=True,
               env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-'))
loader = work/'live-microphone-overlay71.ko'
imports = [line.split()[-1] for line in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(loader)],text=True).splitlines()]
modules['modules'][loader.name] = {'sha256':sha(loader),'imports':imports,'exports':[],
    'vermagic':subprocess.check_output(['modinfo','-F','vermagic',str(loader)],text=True).strip()}
modules['status']='PACKAGED_NOT_LOADED_NO_CAPTURE_ROUTE'
modules['foundation']=foundation
modules['live_build_id']='a9d64cc356f19af79458d365acdec4e771b24be7e377707141a2df40dd39f244'
(work/'manifest.json').write_text(json.dumps(modules,indent=2)+'\n')
with tarfile.open(work/'runtime.tar','w') as tar:
    tar.add(work/'manifest.json',arcname='manifest.json')
    for name,entry in modules['modules'].items():
        source = loader if name==loader.name else root/'out/live-microphone71/modules'/name
        assert sha(source)==entry['sha256']
        tar.add(source,arcname='modules/'+name)
    overlay=root/'out/microphone-foundation71/tb378fc-microphone-foundation71.dtbo'
    assert sha(overlay)==foundation['overlay_sha256']
    tar.add(overlay,arcname=overlay.name)
    tar.add(root/'tools/load-microphone-foundation71.py',arcname='load-foundation.py')
print(json.dumps({'status':modules['status'],'archive_sha256':sha(work/'runtime.tar'),
                  'modules':len(modules['modules'])}))
