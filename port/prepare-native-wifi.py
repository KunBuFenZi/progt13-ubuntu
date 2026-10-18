#!/usr/bin/env python3
"""Stage native WLAN files, including the ODM board actually loaded by Android."""
import hashlib
import argparse
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,default=ROOT/'out/wifi-native-v2')
args=p.parse_args()
out=args.output.resolve()
assert not out.exists(),'Refusing to replace a frozen native firmware set'
vendor=ROOT/'diagnostics/firmware/wifi-peach'
odm=ROOT/'diagnostics/firmware/wifi-odm'
v=json.loads((vendor/'manifest.json').read_text())
o=json.loads((odm/'manifest.json').read_text())
evidence=ROOT/'diagnostics/android-wifi-board-selection.txt'
assert hashlib.sha256(evidence.read_bytes()).hexdigest()==o['selection_evidence']['sha256']
prefix='ath12k/WCN7860/hw2.0/'
mapping=[(vendor,v,'amss20.bin','amss.bin'),(vendor,v,'phy_ucode20.elf','m3.bin'),
         (vendor,v,'aux_ucode20.elf','aux_ucode.bin'),
         (vendor,v,'qdss_trace_config_v2.cfg','qdss.cfg'),
         (odm,o,'bdwlan.elf','board.bin'),(odm,o,'regdb.bin','regdb.bin')]
assert 'found /vendor/firmware_mnt/image/peach/qdss_trace_config_v2.cfg for ' in evidence.read_text()
files={}
for directory,manifest,source,target in mapping:
    p=directory/source;record=manifest[source]
    assert hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256']
    assert p.stat().st_size==record['size']
    dest=out/(prefix+target);dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(p,dest)
    files[prefix+target]=record
result={'hardware':'WCN7860 hw2.0','qmi_chip_id':2,'qmi_board_id':255,
 'status':'NATIVE_FIRMWARE_STAGED_NOT_YET_NETWORK_VALIDATED',
 'board_selection':'Kernel API1 board.bin contains unchanged ODM bdwlan.elf observed in native boot log',
 'selection_evidence_sha256':o['selection_evidence']['sha256'],'files':files}
(out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
