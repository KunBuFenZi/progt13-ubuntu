#!/usr/bin/env python3
"""Select only video diagnostic binaries and parser plugin, not capture plugins."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
root=Path(__file__).resolve().parent.parent
work=root/'out/media-tools68-stage';work.mkdir(exist_ok=False)
with tarfile.open(root/'out/media-tools68-packages.tar.gz') as t:
    for m in t:
        assert m.isfile() and Path(m.name).name==m.name and m.name.endswith('.deb')
        p=work/m.name;p.write_bytes(t.extractfile(m).read())
        subprocess.run(['dpkg-deb','-x',str(p),str(work/'full')],check=True)
selected=['usr/bin/v4l2-ctl','usr/bin/v4l2-compliance',
          'usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstvideoparsersbad.so']
manifest={}
with tarfile.open(work/'runtime.tar.gz','w:gz') as t:
    for rel in selected:
        p=work/'full'/rel
        assert p.is_file()
        name='bin/'+p.name if '/bin/' in rel else 'plugins/'+p.name
        t.add(p,arcname=name)
        manifest[name]=hashlib.sha256(p.read_bytes()).hexdigest()
(work/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('SELECTED_VIDEO_TOOLS',manifest,flush=True)
