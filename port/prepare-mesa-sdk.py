#!/usr/bin/env python3
"""Resume dependency preparation after an identified build-root setup failure."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'upstream/tools/lib'))
import build_root

pins=json.loads((ROOT/'upstream/packaging/mesa/build-root.json').read_text())
work=ROOT/'out/mesa-root-build'
root=work/'root'
assert root.is_dir() and not (work/'root.json').exists()
base=ROOT/'upstream/cache'/pins['build_root']['archive']
assert build_root.sha256(base)==pins['build_root']['sha256']
assert 'VERSION_ID="26.04"' in (root/'etc/os-release').read_text()
assert build_root.capture(root,'dpkg --print-architecture').strip()=='arm64'
log=work/'resume-sdk.log'
packages=' '.join(pins['apt']['packages'])
build_root.chroot(root,'apt-get install -y -q '+packages+' && dpkg --audit',log=log)
audit=build_root.capture(root,'dpkg --audit')
assert not audit.strip(),audit
marker={'build_root':pins['build_root'],'apt':pins['apt']}
(work/'root.json').write_text(json.dumps(marker,indent=2)+'\n')
print('PINNED_MESA_SDK_READY',flush=True)
