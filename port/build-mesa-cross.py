#!/usr/bin/env python3
"""Cross-build the pinned desktop Freedreno against the verified ARM64 SDK."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parent.parent
out=ROOT/'out/mesa-cross'
sdk=ROOT/'out/mesa-root-build/root'
pin=ROOT/'upstream/packaging/mesa'
lock=json.loads((pin/'source.json').read_text())
archive=ROOT/'upstream/cache/mesa'/lock['archive']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(command,**kwargs):
    print('+ '+' '.join(map(str,command)),flush=True)
    subprocess.run(list(map(str,command)),check=True,**kwargs)
assert sha(archive)==lock['sha256']
assert (ROOT/'out/mesa-root-build/root.json').is_file()
for patch in lock['patches']:assert sha(pin/patch['file'])==patch['sha256']
out.mkdir(exist_ok=True)
native=out/'native-tools'
native.mkdir(exist_ok=True)
if not (native/'mesonbuild').exists():
    shutil.copytree(sdk/'usr/lib/python3/dist-packages/mesonbuild',native/'mesonbuild',
                    ignore=shutil.ignore_patterns('__pycache__'))
meson=['/usr/bin/python3','-m','mesonbuild.mesonmain']
scanner=native/'wayland-scanner'
scanner.write_text('#!/bin/sh\nexec /usr/bin/qemu-aarch64 -L '+str(sdk)+' '
                   +str(sdk)+'/usr/bin/wayland-scanner "$@"\n')
scanner.chmod(0o755)
env=dict(os.environ,PYTHONPATH=str(native),PYTHONHASHSEED='0',
         PATH=str(native)+':'+os.environ['PATH'])
wrapper=out/'pkg-config-target'
wrapper.write_text('#!/bin/sh\nexport PKG_CONFIG_SYSROOT_DIR='+str(sdk)+'\n'
                  'export PKG_CONFIG_LIBDIR='+str(sdk)+'/usr/lib/aarch64-linux-gnu/pkgconfig:'
                  +str(sdk)+'/usr/share/pkgconfig\nexec /usr/bin/pkg-config "$@"\n')
wrapper.chmod(0o755)
cross=out/'cross.ini'
cross.write_text(f'''[binaries]
c = ['aarch64-linux-gnu-gcc', '--sysroot={sdk}']
cpp = ['aarch64-linux-gnu-g++', '--sysroot={sdk}']
ar = 'aarch64-linux-gnu-ar'
strip = 'aarch64-linux-gnu-strip'
pkg-config = '{wrapper}'
exe_wrapper = ['qemu-aarch64', '-L', '{sdk}']
[host_machine]
system = 'linux'
cpu_family = 'aarch64'
cpu = 'aarch64'
endian = 'little'
[properties]
needs_exe_wrapper = true
''')
prefix='/usr/lib/erhai/mesa'
flags=[f'--prefix={prefix}','--libdir=lib','--buildtype=release','--wrap-mode=nofallback',
 '-Db_ndebug=false','-Dgallium-drivers=freedreno','-Degl=enabled','-Dgbm=enabled',
 '-Dgles1=disabled','-Dgles2=enabled','-Dllvm=disabled','-Dgallium-va=disabled',
 '-Dvideo-codecs=[]','-Dvalgrind=disabled','-Dbuild-tests=false','-Dplatforms=wayland,x11',
 '-Dglx=dri','-Dglvnd=enabled','-Dvulkan-drivers=[]','-Dspirv-tools=disabled',
 f'-Dc_link_args=-Wl,-rpath,{prefix}/lib',f'-Dcpp_link_args=-Wl,-rpath,{prefix}/lib']
def version(command):return subprocess.check_output(command,text=True,env=env).splitlines()[0]
identity={'source':lock,'profile':'desktop','flags':flags,
 'recipe_sha256':sha(__file__),'cross_file_sha256':sha(cross),
 'sdk_marker_sha256':sha(ROOT/'out/mesa-root-build/root.json'),
 'wayland_scanner_sdk_sha256':sha(sdk/'usr/bin/wayland-scanner'),
 'tools':{'cc':version(['aarch64-linux-gnu-gcc','--version']),
          'cxx':version(['aarch64-linux-gnu-g++','--version']),
          'meson':version([*meson,'--version']),'ninja':version(['ninja','--version'])},
 'native_packages':subprocess.check_output(['dpkg-query','-W','-f=${Package} ${Version}\\n'],text=True).splitlines(),
 'build_method':'native x86_64 generators and compiler, ARM64 Ubuntu SDK target libraries'}
record=out/'input.json'
if record.exists() and json.loads(record.read_text())!=identity:
    # A failed configuration has no compiled output to reuse. Preserve its
    # identity and reconfigure the same pinned source with the corrected tools.
    assert not (out/'build/build.ninja').exists(),'Cross inputs changed after configuration'
    assert json.loads(record.read_text())['source']==identity['source']
    (out/('input-prior-'+sha(record)[:12]+'.json')).write_bytes(record.read_bytes())
    record.write_text(json.dumps(identity,indent=2)+'\n')
src=out/('mesa-'+lock['version'])
if not record.exists():
    assert not src.exists(),'Unidentified cross source tree'
    with tarfile.open(archive) as t:
        epoch=int(t.getmember('mesa-'+lock['version']+'/VERSION').mtime)
        # Pinned archive digest is verified above. Python 3.11.2 has no filter API.
        t.extractall(out)
    for patch in lock['patches']:run(['patch','-p1','--batch','--fuzz=0','-i',pin/patch['file']],cwd=src)
    record.write_text(json.dumps(identity,indent=2)+'\n')
    (out/'source-date-epoch').write_text(str(epoch))
env.update(SOURCE_DATE_EPOCH=(out/'source-date-epoch').read_text(),
           CFLAGS=f'-ffile-prefix-map={src}=/mesa',CXXFLAGS=f'-ffile-prefix-map={src}=/mesa')
build=out/'build'
if not (build/'build.ninja').exists():run([*meson,'setup',build,src,'--cross-file',cross,*flags],env=env)
run([*meson,'compile','-C',build,'-j','2'],env=env)
stage=out/'stage'
run([*meson,'install','-C',build,'--no-rebuild','--destdir',stage],env=env)
files={str(p.relative_to(stage)):sha(p) for p in sorted(stage.rglob('*')) if p.is_file() and not p.is_symlink()}
links={str(p.relative_to(stage)):os.readlink(p) for p in sorted(stage.rglob('*')) if p.is_symlink()}
result={'status':'OFFLINE_BUILD_ONLY','version':lock['version'],'profile':'desktop','prefix':prefix,
 'input_sha256':sha(record),'files_sha256':files,'symlinks':links}
(out/'build-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'staged_files':len(files)}),flush=True)
