#!/usr/bin/env python3
"""Build an isolated continuous DFPS trial; never load or switch the device."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parent.parent
work = root / 'out/refresh-live76'
work.mkdir(exist_ok=False)
kernel = root / 'kernel'
sdk = root / 'out/kernel-usbc70b'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins = {
    'drivers/gpu/drm/msm/disp/dpu1/dpu_encoder.c': '334e8e20867bd2159d1ba6eb8705c8f040cbc2a1af3ea2661ad4913cb72129c5',
    'drivers/gpu/drm/msm/disp/dpu1/dpu_hw_intf.c': 'bfba5fb9089248f07e9e43b3dbc5a5a9c791ac24426efa1c237e053b033d8e21',
    'drivers/gpu/drm/msm/dsi/dsi_host.c': 'c0abb49f91ddda2ca6e8dec4bf7272e726ae0522e68d88933fa40849bc0351ea',
}
assert sha(sdk / 'arch/arm64/boot/Image') == '21c91b2dddf71e38ed6ae4366135a56ec9e02fe9d617bba33937b3e40c6483e9'
for name, digest in pins.items():
    assert sha(kernel / name) == digest, name
encoder = (kernel / 'drivers/gpu/drm/msm/disp/dpu1/dpu_encoder.c').read_text()
prefix = encoder.split('struct dpu_encoder_virt {', 1)[1].split('struct dpu_encoder_phys *cur_slave;', 1)[0]
header = (root / 'port/refresh-seamless76.h').read_text()
candidate = header.split('struct encoder_prefix76 {', 1)[1].split('struct dpu_encoder_phys *cur_slave;', 1)[0]
normalize = lambda s: re.sub(r'\s+', '', s).replace('MAX_PHYS_ENCODERS_PER_VIRTUAL', '4')
assert normalize(prefix) == normalize(candidate)
for name in ['refresh-live76.c', 'refresh-seamless76.h']:
    (work / name).write_bytes((root / 'port' / name).read_bytes())
(work / 'Makefile').write_text('obj-m += refresh-live76.o\n'
    'ccflags-y += -I$(src)/../../kernel/drivers/gpu/drm/msm '
    '-I$(src)/../../out/kernel-usbc70b/drivers/gpu/drm/msm '
    '-I$(src)/../../out/kernel-usbc70b/drivers/gpu/drm/msm/generated\n')
symvers = sdk / 'Module.symvers'
saved = symvers.read_bytes()
try:
    symvers.write_bytes((sdk / 'vmlinux.symvers').read_bytes())
    subprocess.run(['make', '-C', str(kernel), 'O=' + str(sdk), 'LOCALVERSION=+',
                    '-j2', 'M=' + str(work), 'modules'], check=True,
                   env=dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-'))
finally:
    symvers.write_bytes(saved)
module = work / 'refresh-live76.ko'
needed = {l.split()[-1] for l in subprocess.check_output(['aarch64-linux-gnu-nm', '-u', str(module)], text=True).splitlines()}
exports = {l.split()[1] for l in (sdk / 'vmlinux.symvers').read_text().splitlines()}
assert not needed - exports, needed - exports
assert subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip() == '7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
record = {'status': 'BUILT_NOT_LOADED', 'module_sha256': sha(module), 'pinned_live_sources': pins,
          'source_sha256': {n: sha(work / n) for n in ['refresh-live76.c', 'refresh-seamless76.h']},
          'imports': sorted(needed), 'scope': 'Checked same-topology continuous DPU/DSI timing updates; opt-in RAM experiment',
          'default_modes': [60, 120], '144_requires_opt_in': True,
          'does_not_change_mode_at_load': True, 'default_armed': False,
          'baseline_image_and_exports_unchanged': True,
          'restore_policy': 'Return to120 while armed; wait for commit; remove hooks only with display active at120'}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: v for k, v in record.items() if k != 'imports'}, indent=2))
