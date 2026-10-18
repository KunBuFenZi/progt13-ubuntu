#!/usr/bin/env python3
"""Package the verified native flash modules and local desktop controls."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parent.parent
out = root/'out/flash-runtime70'
out.mkdir(exist_ok=False)
sha = lambda data: hashlib.sha256(data).hexdigest()
entries = {}
with tarfile.open(root/'out/live-flash70c.tar') as archive:
    manifest = json.load(archive.extractfile('manifest.json'))
    assert manifest['kernel_image_sha256'] == json.loads((root/'out/boot-usbc70/manifest.json').read_text())['inputs']['kernel']['sha256']
    for name, info in manifest['modules'].items():
        data = archive.extractfile(name).read()
        assert sha(data) == info['sha256']
        entries['usr/local/lib/tb378fc/flash70/'+name] = (data,0o644)
    data = archive.extractfile('tb378fc-flash70.dtbo').read()
    assert sha(data) == manifest['overlay_sha256']
    entries['usr/lib/firmware/tb378fc-flash70.dtbo'] = (data,0o644)
for path in (root/'port/torch70').iterdir():
    if not path.is_file():
        continue
    if path.suffix in ('.service','.socket'):
        name = 'etc/systemd/system/'+path.name
        mode = 0o644
    elif path.suffix == '.desktop':
        name = 'usr/local/share/applications/'+path.name
        mode = 0o644
    else:
        name = 'usr/local/libexec/'+path.name
        mode = 0o755
    entries[name] = (path.read_bytes(),mode)
with tarfile.open(out/'runtime.tar','w') as archive:
    for name,(data,mode) in sorted(entries.items()):
        item = tarfile.TarInfo(name)
        item.mode = mode
        item.size = len(data)
        archive.addfile(item,io.BytesIO(data))
record = {'status':'RUNTIME_PACKAGE_NOT_IN_BOOT_SETTINGS',
          'kernel_image_sha256':manifest['kernel_image_sha256'],
          'tar_sha256':sha((out/'runtime.tar').read_bytes()),
          'files':{name:{'sha256':sha(data),'mode':mode} for name,(data,mode) in entries.items()},
          'torch_total_uA':100000,'torch_auto_off_seconds':30,
          'scope':'Native default-off flash and unprivileged desktop torch; physical light confirmation pending'}
(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'archive':'out/flash-runtime70/runtime.tar','sha256':record['tar_sha256']}))
