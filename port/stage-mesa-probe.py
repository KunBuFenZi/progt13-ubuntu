#!/usr/bin/env python3
"""Package only verified private Mesa libraries and the explicit rendering probe."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,default=Path('out/mesa-cross'))
args=p.parse_args()
ROOT=Path(__file__).resolve().parent.parent
build=args.build.resolve();stage=build/'stage'
result=json.loads((build/'build-result.json').read_text())
identity=json.loads((build/'input.json').read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert result['input_sha256']==sha(build/'input.json')
assert result['profile']=='desktop' and result['prefix']=='/usr/lib/erhai/mesa'
assert identity['source']==json.loads((ROOT/'upstream/packaging/mesa/source.json').read_text())
for name,digest in result['files_sha256'].items():assert sha(stage/name)==digest,name
for name,target in result['symlinks'].items():assert (stage/name).is_symlink() and (stage/name).readlink().as_posix()==target,name
out=ROOT/'out/desktop-serve'
out.mkdir(exist_ok=True)
target=out/'mesa-probe.tar'
assert not target.exists(),'Refusing to replace a published test payload'
prefix='usr/lib/erhai/mesa/'
helpers=[(ROOT/'port/render-probe.py','tb378fc-render-probe.py'),
         (ROOT/'port/mesa-hardware-probe.sh','tb378fc-mesa-hardware-probe'),
         (ROOT/'upstream/packaging/erhai-mesa/tree/usr/lib/systemd/user-environment-generators/80-erhai-mesa','tb378fc-mesa-user-env')]
names=[n for n in sorted(set(result['files_sha256'])|set(result['symlinks']))
       if n.startswith(prefix) and (('/lib/' in n and '.so' in Path(n).name)
        or '/share/glvnd/' in n or '/share/drirc.d/' in n)]
assert names and not any('vulkan' in n.lower() for n in names)
with tarfile.open(target,'w') as archive:
    dirs=set()
    for name in names+['usr/local/libexec/'+name for _,name in helpers]:
        dirs.update(str(p) for p in Path(name).parents if str(p)!='.')
    for directory in sorted(dirs,key=lambda n:(n.count('/'),n)):
        info=tarfile.TarInfo(directory);info.type=tarfile.DIRTYPE;info.mode=0o755;archive.addfile(info)
    for name in names:archive.add(stage/name,arcname=name,recursive=False)
    for source,name in helpers:
        data=source.read_bytes();info=tarfile.TarInfo('usr/local/libexec/'+name)
        info.size=len(data);info.mode=0o755;archive.addfile(info,io.BytesIO(data))
manifest={'status':'READY_FOR_RAM_HARDWARE_TEST_NOT_YET_VALIDATED','sha256':sha(target),
          'size':target.stat().st_size,'build_input_sha256':sha(build/'input.json'),
          'files':names,'helpers_sha256':{name:sha(source) for source,name in helpers},
          'activation':'Explicit per-process environment only; does not switch GNOME automatically'}
(out/'mesa-probe.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:manifest[k] for k in ['status','sha256','size']}))
