#!/usr/bin/env python3
"""Record the completed memory/display build after its final incremental make."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parent.parent
assert subprocess.check_output(['git','-C',str(ROOT/'kernel'),'rev-parse','HEAD'],text=True).strip()=='958a2b4654196bb52dfa0217a0f65ffeaa919f81'
manifest=json.loads((ROOT/'out/keys-build.json').read_text())
image=ROOT/'out/kernel-memory/arch/arm64/boot/Image'
assert b'KMS IOVA aperture ' in image.read_bytes()
config=(ROOT/'out/kernel-memory/.config').read_text().splitlines()
assert {'CONFIG_ZRAM=y','CONFIG_ZSMALLOC=y','CONFIG_ZRAM_DEF_COMP="lz4"','CONFIG_PSI=y'}<=set(config)
manifest.update(status='DISPLAY_IOVA_AND_BOUNDED_ZRAM_BUILD_ONLY_NOT_DEVICE_TESTED')
for p in ['out/kernel-memory/arch/arm64/boot/Image','out/kernel-memory/.config',
          'port/tb378fc-memory.config','port/build-memory.sh','port/finalize-memory.py',
          'port/continue-memory.sh','port/fix-display-iova.py',
          'kernel/drivers/gpu/drm/msm/msm_kms.c']:
    path=ROOT/p
    manifest['files'][p]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':path.stat().st_size}
(ROOT/'out/memory-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('MEMORY_AND_DISPLAY_IOVA_BUILD_VERIFIED_OFFLINE')
