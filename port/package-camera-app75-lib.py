#!/usr/bin/env python3
"""Freeze a stripped camera-only userspace runtime and reproducible source diff."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

root = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--revision', required=True)
args = p.parse_args()
assert args.revision.isalnum()
w = root / 'out/camera-app75'
dest = w / ('runtime-' + args.revision)
dest.mkdir()
for name in ['port/build-camera-app75.py', 'port/tune-camera-app75.py',
             'reference/camera75/stock-colour-matrices.json']:
    shutil.copy2(root / name, dest / Path(name).name)
prefix = Path('usr/lib/tb378fc/camera75')
stage = dest / 'stage'
for name in ['lib', 'libexec', 'share']:
    shutil.copytree(w / 'stage' / prefix / name, stage / prefix / name, symlinks=True)
for path in (stage / prefix).rglob('*'):
    if path.is_file() and not path.is_symlink() and path.read_bytes()[:4] == b'\x7fELF':
        subprocess.run(['aarch64-linux-gnu-strip', '--strip-unneeded', str(path)], check=True)
archive = dest / 'libcamera-runtime.tar.gz'
with tarfile.open(archive, 'w:gz') as t: t.add(stage / prefix, arcname=str(prefix))
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
source = next(w.glob('libcamera-v0.7.0-*'))
patch = []
original = root / 'reference/camera75/libcamera_0.7.0.orig.tar.gz'
assert sha(original) == 'ebd90a3aa2ca87a39323ffb7a4f5bbf72090b43a2431133759620b63e982db87'
with tarfile.open(original) as t:
    for item in t:
        if not item.isfile(): continue
        path = source / Path(item.name).relative_to(source.name)
        before = t.extractfile(item).read()
        if before == path.read_bytes(): continue
        patch.extend(difflib.unified_diff(before.decode().splitlines(True), path.read_text().splitlines(True),
                                          fromfile='a/' + str(path.relative_to(source)), tofile='b/' + str(path.relative_to(source))))
for name in ['gc08a8.yaml', 'ov13b10.yaml']:
    path = source / 'src/ipa/simple/data' / name
    if path.exists():
        patch.extend(difflib.unified_diff([], path.read_text().splitlines(True),
                                          fromfile='/dev/null', tofile='b/' + str(path.relative_to(source))))
(dest / 'libcamera.patch').write_text(''.join(patch))
patch = []
for path in (w / 'camss').iterdir():
    if path.suffix not in ['.c', '.h']: continue
    base = root / 'out/camera74/camss' / path.name
    if not base.exists() or base.read_bytes() == path.read_bytes(): continue
    patch.extend(difflib.unified_diff(base.read_text().splitlines(True), path.read_text().splitlines(True),
                                      fromfile='a/' + path.name, tofile='b/' + path.name))
(dest / 'camss-frame-alignment.patch').write_text(''.join(patch))
manifest = {'source_sha256': sha(original), 'runtime_sha256': sha(archive),
            'recipe_sha256': sha(root / 'port/build-camera-app75.py'),
            'colour_recipe_sha256': sha(root / 'port/tune-camera-app75.py'),
            'stock_colour_metadata_sha256': sha(root / 'reference/camera75/stock-colour-matrices.json'),
            'files': {p.relative_to(stage).as_posix(): sha(p) for p in stage.rglob('*')
                      if p.is_file() and not p.is_symlink()},
            'symlinks': {p.relative_to(stage).as_posix(): str(p.readlink()) for p in stage.rglob('*') if p.is_symlink()},
            'libcamera_patch_sha256': sha(dest / 'libcamera.patch'),
            'camss_patch_sha256': sha(dest / 'camss-frame-alignment.patch'),
            'status': 'BUILT_NOT_DEPLOYED', 'microphone_stream_opened': False}
(dest / 'libcamera-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'runtime_sha256': manifest['runtime_sha256'], 'size': archive.stat().st_size}))
