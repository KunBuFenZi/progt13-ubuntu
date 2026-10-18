#!/usr/bin/env python3
"""Build pinned SSC software in a separate ARM64 SDK; include no OnePlus ROM data."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root/'upstream/tools/lib'))
import build_root
work = root/'out/sensor-stack67'
work.mkdir(exist_ok=True)
lock_path = root/'port/sensor-sources.json'
lock = json.loads(lock_path.read_text())
commit = 'adc57231281ac5bc8eb8ee012ffb04663e9f8226'
cache = work/'inputs'
cache.mkdir(exist_ok=True)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def fetch(urls, target, expected):
    if target.exists():
        assert digest(target) == expected, target
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in urls:
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'TB378FC-mainline-build'})
            with urllib.request.urlopen(request, timeout=40) as response:
                data = response.read(32 * 1024 * 1024)
            assert hashlib.sha256(data).hexdigest() == expected, 'Source digest mismatch'
            target.write_bytes(data)
            return
        except Exception as error:
            errors.append(f'{url}: {error}')
    raise RuntimeError('; '.join(errors))

reference_archive = cache/'oneplus-sensor-reference.tar.gz'
if any(not (cache/p['file']).exists() for s in lock['sources'] for p in s['patches']):
    request = urllib.request.Request('https://codeload.github.com/yzddmr6/onepluspad-2pro-mainline/tar.gz/' + commit,
                                    headers={'User-Agent': 'TB378FC-mainline-build'})
    with urllib.request.urlopen(request, timeout=40) as response:
        reference_data = response.read(64 * 1024 * 1024)
    reference_archive.write_bytes(reference_data)
    with tarfile.open(fileobj=io.BytesIO(reference_data)) as archive:
        members = {m.name.split('/', 1)[1]: m for m in archive.getmembers() if '/' in m.name}
        for source in lock['sources']:
            for patch in source['patches']:
                data = archive.extractfile(members['packaging/sensors/' + patch['file']]).read()
                assert hashlib.sha256(data).hexdigest() == patch['sha256'], patch['file']
                target = cache/patch['file']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    print('PINNED_REFERENCE_PATCHES_READY', flush=True)

for source in lock['sources']:
    urls = [source['url']]
    if 'github.com/' in urls[0] and '/archive/' in urls[0]:
        repo, revision = urls[0].removeprefix('https://github.com/').split('/archive/')
        urls.insert(0, 'https://codeload.github.com/' + repo + '/tar.gz/' + revision.removesuffix('.tar.gz'))
    if source.get('mirror_url'):
        urls.append(source['mirror_url'].replace('http:', 'https:'))
    fetch(urls, cache/source['archive'], source['sha256'])
    for patch in source['patches']:
        url = f'https://raw.githubusercontent.com/yzddmr6/onepluspad-2pro-mainline/{commit}/packaging/sensors/' + patch['file']
        assert digest(cache/patch['file']) == patch['sha256'], patch['file']
    print('PINNED_SOURCE_READY', source['name'], flush=True)

sdk = work/'root'
parent = root/'out/mesa-root-build'
assert json.loads((parent/'root.json').read_text())['build_root'] == lock['build_root']
assert json.loads((parent/'root.json').read_text())['apt']['snapshot'] == lock['apt']['snapshot']
if not sdk.exists():
    subprocess.run(['cp', '-a', '--reflink=auto', str(parent/'root'), str(sdk)], check=True)
assert 'VERSION_ID="26.04"' in (sdk/'etc/os-release').read_text()
marker = work/'sdk-ready.json'
if not marker.exists():
    build_root.chroot(sdk, 'apt-get update -q && apt-get install -y -q ' + ' '.join(lock['apt']['packages']) + ' && dpkg --audit',
                      log=work/'sdk-prepare.log')
    marker.write_text(json.dumps({'parent_sdk_sha256': digest(parent/'root.json'), 'lock_sha256': digest(lock_path)}, indent=2)+'\n')
else:
    assert json.loads(marker.read_text())['lock_sha256'] == digest(lock_path)

prefix = '/usr/lib/tb378fc/sensors'
build_dir = sdk/'tb378fc-build'
build_dir.mkdir(exist_ok=True)
script = ['set -euo pipefail', 'cd /tb378fc-build']
for source in lock['sources']:
    target = build_dir/source['directory']
    if not target.exists():
        with tarfile.open(cache/source['archive']) as archive:
            entries = archive.getmembers()
            assert all(not m.name.startswith('/') and '..' not in Path(m.name).parts for m in entries)
            archive.extractall(build_dir)
        for patch in source['patches']:
            subprocess.run(['patch', '-d', str(target), '-p1', '--batch', '--fuzz=0', '-i', str(cache/patch['file'])], check=True)
    name = source['name']
    output = name + '-build'
    options = ''
    if name == 'iio-sensor-proxy':
        options = ' -Dssc-support=enabled -Dudevrulesdir=/usr/lib/tb378fc/sensors/unused/udev -Dsystemdsystemunitdir=/usr/lib/tb378fc/sensors/unused/systemd'
    script += [
        f'if [ ! -f {output}/build.ninja ]; then PKG_CONFIG_PATH={prefix}/lib/pkgconfig meson setup {output} {source["directory"]} --prefix={prefix} --libdir=lib --bindir=bin --libexecdir=libexec --buildtype=release --wrap-mode=nofallback -Dc_link_args=-Wl,-rpath,{prefix}/lib{options}; fi',
        f'meson compile -C {output} -j 4',
        f'meson install -C {output} --no-rebuild',
        f'meson install -C {output} --no-rebuild --destdir /tb378fc-stage',
    ]
    if name == 'hexagonrpc':
        script.append(f'meson test -C {output} --print-errorlogs')
    elif name == 'libssc':
        script.append(f'./{output}/tests/tests-delivery')
build_root.chroot(sdk, '\n'.join(script), log=work/'compile.log')
stage = sdk/'tb378fc-stage'
files = {p.relative_to(stage).as_posix(): digest(p) for p in stage.rglob('*') if p.is_file() and not p.is_symlink()}
manifest = {'status': 'OFFLINE_BUILD_ONLY_NO_DEVICE_ATTACH', 'reference_commit': commit,
            'source_lock_sha256': digest(lock_path), 'prefix': prefix,
            'rom_data_included': False, 'files_sha256': files}
(work/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
with tarfile.open(work/'sensor-runtime.tar.gz', 'w:gz') as archive:
    for rel in ['bin/hexagonrpcd', 'bin/ssccli', 'libexec/iio-sensor-proxy']:
        archive.add(stage/prefix.lstrip('/')/rel, arcname=prefix.lstrip('/')+'/'+rel)
    for path in (stage/prefix.lstrip('/')/'lib').glob('*.so*'):
        archive.add(path, arcname=prefix.lstrip('/')+'/lib/'+path.name)
print(json.dumps({'status': manifest['status'], 'runtime_sha256': digest(work/'sensor-runtime.tar.gz')}), flush=True)
