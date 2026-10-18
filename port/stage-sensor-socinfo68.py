#!/usr/bin/env python3
"""Serve this unit's measured platform attributes before the first DSP attach."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import grp

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=Path('/usr/share/tb378fc/sensors/hexagonrpcd/socinfo'))
args=parser.parse_args()
sys=Path('/sys/devices/soc0')
dbg=Path('/sys/kernel/debug/qcom_socinfo')
values={}
sources={}
for attr in ('soc_id','revision'):
    p=sys/attr;value=p.read_text().strip();assert re.fullmatch(r'[0-9.]+',value)
    values[attr]=value+'\n';sources[attr]=str(p)
assert values['soc_id'].strip()=='639'
hardware=(dbg/'hardware_platform').read_text().strip()
assert hardware=='11'
# ID 11 is QCOM_BOARD_ID_QRD in the kernel binding. The native Android DT
# captured from this tablet also identifies qcom,sun-qrd/qcom,sunp-qrd.
values['hw_platform']='QRD\n'
sources['hw_platform']={'source':str(dbg/'hardware_platform'),'id':11,
                        'mapping':'include/dt-bindings/arm/qcom,ids.h QCOM_BOARD_ID_QRD',
                        'corroboration':'Native TB378FC Android DT: qcom,sun-qrd / qcom,sunp-qrd'}
for attr,source in [('platform_subtype_id',dbg/'hardware_platform_subtype'),('platform_version',dbg/'platform_version')]:
    value=source.read_text().strip();assert value.isdecimal()
    values[attr]=value+'\n';sources[attr]=str(source)
output=args.output
assert not output.is_symlink()
if output.exists():
    assert output.is_dir() and not any(output.iterdir()), 'Never replace existing platform attributes'
else:
    output.mkdir(parents=True,mode=0o750)
gid=grp.getgrnam('fastrpc').gr_gid
__import__('os').chown(output,0,gid)
for name,value in values.items():
    path=output/name;path.write_text(value);path.chmod(0o640);__import__('os').chown(path,0,gid)
manifest={'status':'REAL_SOCINFO_STAGED_NO_DSP_RESTART','output':str(output),'sources':sources,
          'values':{k:v.strip() for k,v in values.items()},
          'files_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in values.items()},
          'limits':'No platform_subtype string was invented. ALS availability must be queried after next first attach.'}
evidence=Path('/run/evidence/peripherals68/sensor-socinfo-stage.json')
evidence.parent.mkdir(parents=True,exist_ok=True);evidence.write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
