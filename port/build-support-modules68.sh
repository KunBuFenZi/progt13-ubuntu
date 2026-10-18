#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
sdk="$PWD/out/kernel-peripherals68"
test "$(cat logs/media-closure68b.exit)" = 0
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
cp "$sdk/vmlinux.symvers" "$sdk/Module.symvers"
python3 - <<'PY'
from pathlib import Path
import shutil
p=Path('out/bt-prereq68');p.mkdir(exist_ok=False)
for name in ['kpp.c','ecc.c','ecdh.c','ecdh_helper.c']:
    shutil.copy2(Path('kernel/crypto')/name,p/name)
for header in Path('kernel/crypto').glob('*.h'):
    shutil.copy2(header,p/header.name)
shutil.copy2('kernel/lib/crc/crc16.c',p/'crc16.c')
(p/'Makefile').write_text('obj-m += kpp.o ecc.o ecdh_generic.o crc16.o\necdh_generic-y := ecdh.o ecdh_helper.o\n')
PY
make -C kernel O="$sdk" LOCALVERSION=+ -j3 M="$PWD/out/bt-prereq68" modules
make -C kernel O="$sdk" LOCALVERSION=+ -j3 \
 KBUILD_EXTRA_SYMBOLS="$PWD/out/bt-prereq68/Module.symvers" M=net/bluetooth modules
make -C kernel O="$sdk" LOCALVERSION=+ -j3 \
 KBUILD_EXTRA_SYMBOLS="$PWD/out/bt-prereq68/Module.symvers $PWD/kernel/net/bluetooth/Module.symvers" M=drivers/bluetooth modules
make -C kernel O="$sdk" LOCALVERSION=+ -j3 M=drivers/soundwire modules
make -C kernel O="$sdk" LOCALVERSION=+ -j3 M=drivers/soc/qcom modules
make -C kernel O="$sdk" LOCALVERSION=+ -j3 \
 KBUILD_EXTRA_SYMBOLS="$PWD/kernel/drivers/soundwire/Module.symvers $PWD/kernel/drivers/soc/qcom/Module.symvers" \
 M=sound modules
make -C kernel O="$sdk" LOCALVERSION=+ -j3 M="$PWD/out/live-i2c-modules66" modules
mkdir -p out/additive-modules68
cp port/gpu-telemetry67.c out/additive-modules68/tb378fc_gpu_telemetry.c
cp kernel/drivers/misc/fastrpc.c out/additive-modules68/fastrpc.c
printf 'obj-m += tb378fc_gpu_telemetry.o fastrpc.o\n' >out/additive-modules68/Makefile
make -C kernel O="$sdk" LOCALVERSION=+ -j3 M="$PWD/out/additive-modules68" modules
python3 - <<'PY'
import hashlib,json,shutil,subprocess
from pathlib import Path
old=json.loads(Path('out/live-audio-level6/manifest.json').read_text())
paths={}
for directory in ['kernel/sound','kernel/drivers/soundwire','kernel/drivers/soc/qcom','kernel/net/bluetooth',
                  'kernel/drivers/bluetooth','out/live-i2c-modules66','out/additive-modules68','out/media-closure68b','out/bt-prereq68']:
    for p in Path(directory).rglob('*.ko'):
        if p.name in old or p.name in ['socinfo.ko','bluetooth.ko','rfcomm.ko','bnep.ko','hidp.ko','hci_uart.ko','btqca.ko','fastrpc.ko','tb378fc_gpu_telemetry.ko'] or directory.endswith(('media-closure68b','bt-prereq68')):
            assert p.name not in paths,(p.name,paths.get(p.name),str(p))
            paths[p.name]=p
assert set(old)<=set(paths),set(old)-set(paths)
dest=Path('out/runtime-modules68');dest.mkdir(exist_ok=False)
manifest={}
exports={line.split()[1] for line in Path('out/kernel-peripherals68/vmlinux.symvers').read_text().splitlines()}
for name,source in paths.items():
    p=dest/name;shutil.copy2(source,p)
    names=subprocess.check_output(['aarch64-linux-gnu-nm',str(p)],text=True)
    undefined=subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(p)],text=True)
    info={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
          'vermagic':subprocess.check_output(['modinfo','-F','vermagic',str(p)],text=True).strip(),
          'exports':[s.split()[-1].removeprefix('__ksymtab_') for s in names.splitlines() if s.split() and s.split()[-1].startswith('__ksymtab_')],
          'undefined':[s.split()[-1] for s in undefined.splitlines() if s.split()]}
    manifest[name]=info;exports.update(info['exports'])
missing={n:sorted(set(i['undefined'])-exports) for n,i in manifest.items() if set(i['undefined'])-exports}
assert not missing,missing
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('NEW_KERNEL_RUNTIME_MODULES_VERIFIED',len(manifest),flush=True)
PY
