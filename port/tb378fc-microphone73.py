#!/usr/bin/env python3
"""Load checked codecs on a complete boot DT. Never open a capture PCM."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory',type=Path,default=Path('/usr/share/tb378fc/microphone73'))
parser.add_argument('--load',action='store_true')
args=parser.parse_args()
root=args.directory
manifest=json.loads((root/'manifest.json').read_text())
assert b'lenovo,tb378fc-pmic-glink\0' in Path('/proc/device-tree/pmic-glink/compatible').read_bytes()
release=subprocess.check_output(['uname','-r'],text=True).strip()
assert release=='7.2.0-tb378fc-wifi+'
assert not int(Path('/proc/sys/kernel/tainted').read_text())&128, 'Kernel oops already recorded'
assert not Path('/sys/module/live_microphone_capture71').exists()
exports={line.split()[2].removeprefix('__ksymtab_') for line in Path('/proc/kallsyms').read_text().splitlines()
         if line.split()[2].startswith('__ksymtab_')}
loaded={line.split()[0] for line in Path('/proc/modules').read_text().splitlines()}
normalize=lambda name:name.removesuffix('.ko').replace('-','_')
pending={}
for name,entry in manifest['modules'].items():
    assert Path(name).name==name and name.endswith('.ko')
    assert hashlib.sha256((root/'modules'/name).read_bytes()).hexdigest()==entry['sha256'],name
    assert entry['vermagic']==release+' SMP preempt mod_unload aarch64'
    if normalize(name) not in loaded: pending[name]=entry
assert len(manifest['modules'])==14
order=[];available=set(exports)
while pending:
    ready=sorted(name for name,entry in pending.items() if not set(entry['imports'])-available)
    assert ready,{name:sorted(set(entry['imports'])-available) for name,entry in pending.items()}
    for name in ready:
        available.update(pending.pop(name)['exports']);order.append(name)
proof={'time':time.time(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
       'build_id':Path('/etc/tb378fc-build-id').read_text().strip(),
       'status':'IMPORTS_AND_HASHES_VERIFIED_ONLY','order':order,'loaded_now':[],
       'recorded_audio':False,'hot_controller_replacement':False,'codec_unload':False}
out=Path('/run/evidence/microphone73.json');out.parent.mkdir(exist_ok=True)
def save():out.write_text(json.dumps(proof,indent=2)+'\n')
save()
if args.load:
    assert Path('/proc/device-tree/sound/wcd-capture-dai-link').is_dir()
    assert Path('/proc/device-tree/tb378fc-wcd939x').is_dir()
    assert not Path('/proc/device-tree/soc@0/tb378fc-soundwire-tx@7630000').exists()
    for name in order:
        result=subprocess.run(['insmod',str(root/'modules'/name)],capture_output=True,text=True)
        proof['loaded_now'].append({'name':name,'exit':result.returncode,'stderr':result.stderr})
        save()
        if result.returncode:raise SystemExit('Stopped at '+name+': '+result.stderr)
    for attempt in range(36):
        if Path('/proc/asound/pcm').exists() and 'MultiMedia3' in Path('/proc/asound/pcm').read_text():break
        time.sleep(.5)
    proof['pcm']=Path('/proc/asound/pcm').read_text() if Path('/proc/asound/pcm').exists() else None
    proof['soundwire']=[{'name':p.name,'status':(p/'status').read_text().strip() if (p/'status').exists() else None,
                         'driver':(p/'driver').resolve().name if (p/'driver').exists() else None}
                        for p in Path('/sys/bus/soundwire/devices').iterdir()]
    proof['status']='CAPTURE_ENUMERATED_NOT_RECORDED' if proof['pcm'] and 'MultiMedia3' in proof['pcm'] else 'CAPTURE_NOT_ENUMERATED'
    save()
    assert proof['status']=='CAPTURE_ENUMERATED_NOT_RECORDED',proof['status']
print(json.dumps(proof,indent=2))
