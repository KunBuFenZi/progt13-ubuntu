#!/usr/bin/env python3
"""Map the identified ROM 2.0 controller to this tablet ROM's native firmware."""
import hashlib
import json
from pathlib import Path
import subprocess
assert Path('/etc/tb378fc-candidate').read_text().strip()=='peripherals68'
log=subprocess.check_output(['dmesg'],text=True)
for line in ['QCA Product ID   :0x00000021','QCA ROM Version  :0x00000200','QCA SOC Version  :0x40210200']:
    assert line in log,line
source=Path('/usr/lib/firmware/qca/tb378fc')
local=Path('/usr/lib/firmware/qca')
native=Path('/run/native-bluetooth68-manifest.json')
manifest=json.loads(native.read_text())
mapped={}
for p in [source/'brhbtfw20.mbn',*sorted(source.glob('brhbtnv20.*'))]:
    assert p.is_file()
    info=manifest['files']['image/'+p.name]
    assert p.stat().st_size==info['bytes']
    assert hashlib.sha256(p.read_bytes()).hexdigest()==info['sha256']
    name=p.name.replace('brh','gng',1)
    target=local/name
    assert not target.exists() and not target.is_symlink()
    target.symlink_to('tb378fc/'+p.name)
    mapped[name]={'native_file':p.name,'sha256':info['sha256']}
Path('/run/evidence/peripherals68/bt-native-firmware-map.json').write_text(json.dumps({
    'status':'NATIVE_FIRMWARE_MAPPED_NOT_DOWNLOADED_YET','controller_product_id':'0x21',
    'controller_rom_version':'0x200','native_rom_btfm_sha256':manifest['source_sha256'],
    'mapping':mapped,'nvm_policy':'Driver reads real board ID and picks the matching native variant'},indent=2)+'\n')
print('MAPPED_NATIVE_FILES',len(mapped))
