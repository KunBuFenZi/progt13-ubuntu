#!/usr/bin/env python3
"""Test full same-slot boot triplet swaps using host files, never block devices."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
w=root/'out/switch79-tests';w.mkdir(exist_ok=False)
store=w/'store';store.mkdir();devices=w/'devices';devices.mkdir()
script=root/'out/switch79/tb378fc-switch'
record={'scope':'host regular files; no tablet or block devices','steps':[]}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for kind in ['android','ubuntu']:
    d=store/kind;d.mkdir();sums=[]
    for name,size in [('boot',2*1024*1024),('init_boot',1024*1024),('vendor_boot',2*1024*1024)]:
        data=bytearray(hashlib.shake_256((kind+name).encode()).digest(size))
        if name=='boot':
            data[:8]=b'ANDROID!'
            if kind=='ubuntu':data[44:44+len(b'tb378fc.stage=1')]=b'tb378fc.stage=1'
        p=d/(name+'.img');p.write_bytes(data);sums.append(digest(p)+'  '+name+'.img\n')
        if kind=='android':shutil.copy2(p,devices/(name+'_a'))
    (d/'SHA256SUMS').write_text(''.join(sums))
prefix=['sh',str(script),'--store',str(store),'--dev-dir',str(devices),'--slot','_a','--no-reboot']
def run(args,ok=True):
    r=subprocess.run(prefix+args,capture_output=True,text=True,timeout=20)
    record['steps'].append({'args':args,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    assert (r.returncode==0)==ok,(args,r.stdout,r.stderr)
    return r
run(['verify'])
before={p.name:digest(p) for p in devices.iterdir()}
run(['to-ubuntu','--dry-run']);assert before=={p.name:digest(p) for p in devices.iterdir()}
run(['to-ubuntu'])
for p in devices.iterdir():assert digest(p)==digest(store/'ubuntu'/(p.name[:-2]+'.img'))
run(['to-android'])
assert before=={p.name:digest(p) for p in devices.iterdir()}
p=store/'ubuntu/vendor_boot.img';old=p.read_bytes();p.write_bytes(b'corrupt'+old[7:])
run(['to-ubuntu'],False);assert before=={p.name:digest(p) for p in devices.iterdir()};p.write_bytes(old)
(store/'.switch-incomplete').write_text('interrupted\n');run(['to-ubuntu'],False);(store/'.switch-incomplete').unlink()
run(['stash-android'],False)
assert not (store/'android.prev').exists() and not (store/'.android.new').exists()
record['status']='HOST_ROUNDTRIP_DRY_RUN_CORRUPTION_INTERRUPTION_TESTS_PASSED'
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(record['status'])
