#!/usr/bin/env python3
"""Integrate verified live68 fixes without replacing the running boot or relay."""
import copy
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

root=Path(__file__).resolve().parent.parent
base=root/'out/peripherals-package68d/settings.tar'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='out/peripherals-package68e')
args=parser.parse_args()
out=(root/args.output).resolve()
assert out.parent==root/'out' and out.name.startswith('peripherals-package68')
out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(base)=='79e74bf896fb8021dbc9b18847d7528ae2b242a16eb87273311a94356ff6e480'
entries={}
with tarfile.open(base) as archive:
    for item in archive:
        assert not item.name.startswith('/') and '..' not in Path(item.name).parts
        assert not item.name.startswith('var/lib/bluetooth/')
        entries[item.name]=(copy.copy(item),archive.extractfile(item).read() if item.isfile() else None)
epoch=int(time.time())
def add(name,data,mode=0o644):
    if isinstance(data,str):data=data.encode()
    item=tarfile.TarInfo(name);item.size=len(data);item.mode=mode;item.mtime=epoch
    entries[name]=(item,data)
def file(name,source,mode=0o644):add(name,Path(source).read_bytes(),mode)
def link(name,target):
    item=tarfile.TarInfo(name);item.type=tarfile.SYMTYPE;item.mode=0o777;item.mtime=epoch;item.linkname=target
    entries[name]=(item,None)
file('usr/local/libexec/tb378fc-runtime68',root/'port/tb378fc-runtime68',0o755)
# systemd uses the epoch file's mtime, not its content.
add('usr/lib/clock-epoch',str(epoch)+'\n')
uart=root/'out/bt-uart-live68b'
uart_manifest=json.loads((uart/'manifest.json').read_text())
assert sha(uart/'tb378fc_geni_uart.ko')==uart_manifest['module_sha256']
release=(root/'out/kernel-peripherals68/include/config/kernel.release').read_text().strip()
module_path='usr/lib/modules/'+release
file(module_path+'/extra/tb378fc_geni_uart.ko',uart/'tb378fc_geni_uart.ko')
file('usr/share/tb378fc/bt-uart-live68.json',uart/'manifest.json')
with tarfile.open(root/'out/native-bluetooth68.tar.gz') as archive:
    native=json.load(archive.extractfile('manifest.json'))
mapped={}
for name,(item,data) in list(entries.items()):
    source=Path(name).name
    if name.startswith('usr/lib/firmware/qca/tb378fc/') and (source=='brhbtfw20.mbn' or source.startswith('brhbtnv20.')):
        assert hashlib.sha256(data).hexdigest()==native['files']['image/'+source]['sha256']
        alias=source.replace('brh','gng',1)
        link('usr/lib/firmware/qca/'+alias,'tb378fc/'+source)
        mapped[alias]=source
assert len(mapped)==14
add('usr/share/tb378fc/bt-native-map68.json',json.dumps({'product_id':'0x21','rom':'0x200','mapping':mapped},indent=2)+'\n')
file('usr/local/libexec/tb378fc-bluetooth-address68.py',root/'port/tb378fc-bluetooth-address68.py',0o755)
for unit in ('tb378fc-video68','tb378fc-bluetooth68'):
    file('etc/systemd/system/'+unit+'.service',root/'port'/str(unit+'.service'))
    link('etc/systemd/system/graphical.target.wants/'+unit+'.service','../'+unit+'.service')
add('etc/systemd/system/bluetooth.service.d/92-tb378fc-native.conf',
    '[Unit]\nRequires=tb378fc-bluetooth68.service\nAfter=tb378fc-bluetooth68.service\n')
link('etc/systemd/system/graphical.target.wants/bluetooth.service','/usr/lib/systemd/system/bluetooth.service')
# Keep stock video/uaccess rules. No world-writable codec devices.
with tarfile.open(root/'out/media-tools68-stage/runtime.tar.gz') as archive:
    for item in archive:
        assert item.isfile()
        if item.name.startswith('plugins/'):
            target='usr/lib/aarch64-linux-gnu/gstreamer-1.0/'+Path(item.name).name
        else:
            assert item.name.startswith('bin/')
            target='usr/local/bin/'+Path(item.name).name
        add(target,archive.extractfile(item).read(),0o755)
# Recompute module dependencies for the exact checked kernel and added UART.
stage=out/'module-root'
(stage/module_path).mkdir(parents=True)
(stage/'lib').symlink_to('usr/lib',target_is_directory=True)
for name,(item,data) in entries.items():
    if name.startswith(module_path+'/') and item.isfile():
        p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
subprocess.run(['depmod','-b',str(stage),'-F',str(root/'out/kernel-peripherals68/System.map'),release],check=True)
for p in (stage/module_path).glob('modules.*'):
    file(module_path+'/'+p.name,p)
target=out/'settings.tar'
with tarfile.open(target,'w') as archive:
    for name,(item,data) in sorted(entries.items()):
        archive.addfile(item,io.BytesIO(data) if data is not None else None)
record={'status':'OFFLINE_RUNTIME_INTEGRATION_NOT_COLD_BOOT_TESTED',
        'base_settings_sha256':sha(base),'settings_sha256':sha(target),
        'clock_epoch_mtime':epoch,'pairing_keys_included':False,
        'pairing_policy':'Preserved separately in local access-restricted archive; restore before bluetoothd on next test',
        'files_sha256':{name:hashlib.sha256(data).hexdigest() for name,(item,data) in entries.items() if data is not None},
        'recipes_sha256':{p.name:sha(p) for p in (Path(__file__),root/'port/tb378fc-runtime68',root/'port/tb378fc-video68.service',root/'port/tb378fc-bluetooth68.service',root/'port/tb378fc-bluetooth-address68.py')}}
(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('files_sha256','recipes_sha256')},indent=2))
