#!/usr/bin/env python3
"""Package the sole missing runtime library from the verified sensor SDK."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parent.parent
work=root/'out/sensor-stack67'
sdk=work/'root'
ready=json.loads((work/'sdk-ready.json').read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert ready['lock_sha256']==sha(root/'port/sensor-sources.json')
relative='usr/lib/aarch64-linux-gnu/libprotobuf-c.so.1.0.0'
data=(sdk/relative).read_bytes()
md5=hashlib.md5(data).hexdigest()
sums=(sdk/'var/lib/dpkg/info/libprotobuf-c1:arm64.md5sums').read_text().splitlines()
assert f'{md5}  {relative}' in sums
package=next(block for block in (sdk/'var/lib/dpkg/status').read_text().split('\n\n') if block.startswith('Package: libprotobuf-c1\n'))
version=next(line.removeprefix('Version: ') for line in package.splitlines() if line.startswith('Version: '))
name='usr/lib/tb378fc/sensors/lib/libprotobuf-c.so.1'
record={'source':'Verified Ubuntu sensor SDK from pinned signed APT snapshot','version':version,
        'package':'libprotobuf-c1:arm64','sdk_ready':ready,'files_sha256':{name:hashlib.sha256(data).hexdigest()}}
with tarfile.open(work/'sensor-deps.tar.gz','w:gz') as tar:
    info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644
    tar.addfile(info,io.BytesIO(data))
(work/'runtime-deps.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
