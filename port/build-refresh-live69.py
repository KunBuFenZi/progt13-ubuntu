#!/usr/bin/env python3
"""Build the isolated mode-enumeration adapter against the live68 kernel."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='out/refresh-live69')
args=parser.parse_args()
work=(root/args.output).resolve()
assert work.parent==root/'out' and work.name.startswith('refresh-live69')
work.mkdir(exist_ok=False)
source=root/'port/refresh-modes-live69.c'
(work/source.name).write_bytes(source.read_bytes())
(work/'Makefile').write_text('obj-m += refresh-modes-live69.o\nccflags-y += -I'+str(root/'kernel/drivers/gpu/drm/msm')+'\n')
sdk=root/'out/kernel-peripherals68'
(sdk/'Module.symvers').write_bytes((sdk/'vmlinux.symvers').read_bytes())
subprocess.run(['make','-C',str(root/'kernel'),'O='+str(sdk),'LOCALVERSION=+','-j2','M='+str(work),'modules'],
               check=True,env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-'))
module=work/'refresh-modes-live69.ko'
needed={l.split()[-1] for l in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(module)],text=True).splitlines()}
exports={l.split()[1] for l in (sdk/'vmlinux.symvers').read_text().splitlines()}
assert not needed-exports,needed-exports
record={'status':'OFFLINE_LIVE_MODE_ADAPTER_NOT_LOADED','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'module_sha256':hashlib.sha256(module.read_bytes()).hexdigest(),
        'scope':'Only panel get_modes callback under DRM modeset locks; original prepare/enable/power callbacks preserved',
        'restore_policy':'Set120Hz before unloading adapter; no driver unbind or bus writes'}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
