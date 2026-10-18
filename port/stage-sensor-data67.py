#!/usr/bin/env python3
"""Stage only this unit's captured registry and its current Android config."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parent.parent
source=root/'diagnostics/sensors/native-sensor-runtime.tar'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='67b48679c9e028a07341a3f03fc84b4877a84f3afe74cc59555f7e01755d0d08'
prefix='usr/share/tb378fc/sensors/hexagonrpcd'
files={}
with tarfile.open(source) as tar:
    for member in tar.getmembers():
        assert not member.name.startswith('/') and '..' not in Path(member.name).parts
        if not member.isfile():
            continue
        name=member.name
        if name.startswith('mnt/vendor/persist/sensors/registry/registry/'):
            rel='sensors/registry/'+name.rsplit('/',1)[1]
        elif name=='mnt/vendor/persist/sensors/registry/sns_reg_version':
            rel='sensors/sns_reg_version'
        elif name.startswith('vendor/etc/sensors/config/'):
            rel='sensors/config/'+name.rsplit('/',1)[1]
        elif name=='vendor/etc/sensors/sns_reg_config':
            rel='sensors/sns_reg.conf'
        elif name.startswith('odm/etc/sensor/config/'):
            rel='sensors/odm-config/'+name.rsplit('/',1)[1]
        elif name.startswith('sys/devices/soc0/'):
            rel='socinfo/'+name.rsplit('/',1)[1]
        else:
            continue
        assert member.size<=1024*1024
        files[prefix+'/'+rel]=tar.extractfile(member).read()
assert any('/sensors/registry/' in n for n in files)
assert prefix+'/sensors/config/json.lst' in files
assert prefix+'/sensors/sns_reg.conf' in files
manifest={'source_archive_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'unit_data_only':True,'reference_device_data':False,
          'socinfo_files_present':sorted(n for n in files if '/socinfo/' in n),
          'files_sha256':{n:hashlib.sha256(data).hexdigest() for n,data in files.items()}}
target=root/'out/sensor-data67.tar.gz'
assert not target.exists(), 'Do not overwrite prior inputs'
with tarfile.open(target,'w:gz') as tar:
    for name,data in files.items():
        member=tarfile.TarInfo(name); member.size=len(data); member.mode=0o640
        tar.addfile(member,io.BytesIO(data))
(root/'out/sensor-data67.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'files':len(files),'archive_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                  'socinfo_files_present':manifest['socinfo_files_present']}))
