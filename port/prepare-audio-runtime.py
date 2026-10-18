#!/usr/bin/env python3
"""Stage ARM64 aplay/amixer and their ELF closure from the verified Ubuntu root."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
ubuntu = root/'out/desktop-root'
out = root/'out/audio-runtime'
out.mkdir(exist_ok=True)
files = {}
needed = set()

def stage(source, destination, executable=False):
    assert not Path(destination).is_absolute() and '..' not in Path(destination).parts
    data = source.read_bytes()
    target = out/destination
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o755 if executable else 0o644)
    files[destination] = {'sha256':hashlib.sha256(data).hexdigest(),
                          'mode':0o755 if executable else 0o644,
                          'source':source.relative_to(ubuntu).as_posix()}

def elf(source):
    data = source.read_bytes()
    assert data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0] == 183
    dynamic = subprocess.check_output(['aarch64-linux-gnu-readelf','-d',source],text=True)
    needed.update(re.findall(r'\(NEEDED\).*\[([^\]]+)\]',dynamic))

for name in ('aplay','amixer'):
    source = ubuntu/'usr/bin'/name
    elf(source)
    stage(source,'bin/'+name,True)

def library(name):
    for directory in ('usr/lib/aarch64-linux-gnu','lib/aarch64-linux-gnu','usr/lib','lib'):
        source = ubuntu/directory/name
        if source.is_file():
            resolved = source.resolve()
            assert resolved.is_relative_to(ubuntu.resolve()), 'Host library escape'
            return resolved
    raise FileNotFoundError(name)

done = set()
while needed-done:
    name = sorted(needed-done)[0]
    source = library(name)
    elf(source)
    stage(source,'lib/aarch64-linux-gnu/'+name,True)
    done.add(name)
loader = library('ld-linux-aarch64.so.1')
elf(loader)
stage(loader,'lib/ld-linux-aarch64.so.1',True)

for source in (ubuntu/'usr/share/alsa').rglob('*.conf'):
    if not source.is_file() or 'ucm2' in source.relative_to(ubuntu).parts:
        continue
    assert source.resolve().is_relative_to(ubuntu.resolve())
    stage(source,source.relative_to(ubuntu).as_posix())
assert 'usr/share/alsa/alsa.conf' in files
manifest = {'source':'Previously SHA256-verified Ubuntu desktop layers',
            'files':files,'scope':'Only PCM/control tools, libraries and ALSA config; no credentials'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for binary in ('aplay','amixer'):
    result = subprocess.run(['qemu-aarch64','-L',out,out/'bin'/binary,'--version'],
                            capture_output=True,text=True,check=True,timeout=15)
    print(result.stdout.strip())
print('Audio runtime files',len(files),'bytes',sum((out/name).stat().st_size for name in files))
