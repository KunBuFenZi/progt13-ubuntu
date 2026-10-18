#!/usr/bin/env python3
"""Stage this unit's hw2.0 WLAN firmware without selecting board calibration."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parent.parent
source=ROOT/'diagnostics/firmware/wifi-peach'
records=json.loads((source/'manifest.json').read_text())
mapping={'amss20.bin':'amss.bin','phy_ucode20.elf':'m3.bin',
         'aux_ucode20.elf':'aux_ucode.bin','regdb.bin':'regdb.bin'}
out=ROOT/'out/desktop-serve/wifi-probe.tar'
assert not out.exists(),'Refusing to replace a published firmware payload'
prefix='usr/lib/firmware/ath12k/WCN7860/hw2.0'
files={}
with tarfile.open(out,'w') as t:
    for name,target in mapping.items():
        p=source/name;data=p.read_bytes()
        digest=hashlib.sha256(data).hexdigest()
        assert digest==records[name]['sha256'] and len(data)==records[name]['size'],name
        t.add(p,arcname=prefix+'/'+target)
        files[target]={'source':records[name]['source'],'source_name':name,
                       'sha256':digest,'size':len(data)}
manifest={'status':'WCN7860_HW20_FIRMWARE_TEST_NO_BOARD_CALIBRATION',
          'hardware_evidence':'out/device-tests/20261018-014827/serial.log',
          'files':files,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
          'size':out.stat().st_size,'board_data_included':False,
          'scope':'RAM-only firmware loading to read QMI identity; no radio/network acceptance yet'}
out.with_suffix('.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
