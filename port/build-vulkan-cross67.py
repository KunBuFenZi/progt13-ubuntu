#!/usr/bin/env python3
"""Build isolated Turnip from pinned Mesa; never replace the working GL build."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

root = Path(__file__).resolve().parent.parent
work = root/'out/vulkan-cross67'
sdk = root/'out/mesa-root-build/root'
pin = root/'upstream/packaging/mesa'
lock = json.loads((pin/'source.json').read_text())
archive = root/'upstream/cache/mesa'/lock['archive']
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(archive) == lock['sha256']
for patch in lock['patches']:
    assert sha(pin/patch['file']) == patch['sha256']
work.mkdir(exist_ok=True)
native = root/'out/mesa-cross/native-tools'
cross = root/'out/mesa-cross/cross.ini'
meson = ['/usr/bin/python3', '-m', 'mesonbuild.mesonmain']
prefix = '/usr/lib/tb378fc/turnip'
flags = [f'--prefix={prefix}', '--libdir=lib', '--buildtype=release', '--wrap-mode=nofallback',
         '-Db_ndebug=false', '-Dgallium-drivers=[]', '-Dvulkan-drivers=freedreno',
         '-Dfreedreno-kmds=msm', '-Degl=disabled', '-Dgbm=disabled', '-Dgles1=disabled',
         '-Dgles2=disabled', '-Dopengl=false', '-Dglx=disabled', '-Dllvm=disabled',
         '-Dgallium-va=disabled', '-Dvideo-codecs=[]', '-Dvalgrind=disabled',
         '-Dbuild-tests=false', '-Dplatforms=wayland,x11', '-Dglvnd=disabled',
         '-Dspirv-tools=disabled', f'-Dc_link_args=-Wl,-rpath,{prefix}/lib',
         f'-Dcpp_link_args=-Wl,-rpath,{prefix}/lib']
identity = {'source': lock, 'flags': flags, 'recipe_sha256': sha(__file__),
            'cross_sha256': sha(cross), 'sdk_marker_sha256': sha(root/'out/mesa-root-build/root.json')}
record = work/'input.json'
src = work/('mesa-'+lock['version'])
if record.exists():
    assert json.loads(record.read_text()) == identity, 'Preserve build provenance'
else:
    assert not src.exists()
    with tarfile.open(archive) as tar:
        epoch = int(tar.getmember('mesa-'+lock['version']+'/VERSION').mtime)
        tar.extractall(work)
    for patch in lock['patches']:
        subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '-i', str(pin/patch['file'])], cwd=src, check=True)
    record.write_text(json.dumps(identity, indent=2)+'\n')
    (work/'source-date-epoch').write_text(str(epoch))
env = dict(os.environ, PYTHONPATH=str(native), PYTHONHASHSEED='0',
           PATH=str(native)+':'+os.environ['PATH'], SOURCE_DATE_EPOCH=(work/'source-date-epoch').read_text(),
           CFLAGS=f'-ffile-prefix-map={src}=/mesa', CXXFLAGS=f'-ffile-prefix-map={src}=/mesa')
def run(args):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), env=env, check=True)
build = work/'build'
if not (build/'build.ninja').exists():
    run([*meson, 'setup', build, src, '--cross-file', cross, *flags])
run([*meson, 'compile', '-C', build, '-j', '2'])
stage = work/'stage'
run([*meson, 'install', '-C', build, '--no-rebuild', '--destdir', stage])
files = {p.relative_to(stage).as_posix(): sha(p) for p in stage.rglob('*') if p.is_file() and not p.is_symlink()}
with tarfile.open(work/'turnip-runtime.tar.gz', 'w:gz') as tar:
    tar.add(stage/prefix.lstrip('/'), arcname=prefix.lstrip('/'))
result = {'status': 'OFFLINE_BUILD_ONLY', 'input_sha256': sha(record), 'files_sha256': files,
          'runtime_sha256': sha(work/'turnip-runtime.tar.gz')}
(work/'build-result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result), flush=True)
