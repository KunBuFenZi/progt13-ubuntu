#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-live-audio-modules66.exit' EXIT
test "$(cat logs/build-live-audio-kernel66.exit)" = 0
test ! -e out/live-audio-modules66
sdk="$PWD/out/kernel-memory"
cmp "$sdk/.config" out/kernel-live-audio66/.config
cp "$sdk/vmlinux.symvers" "$sdk/Module.symvers"
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
make -C kernel O="$sdk" LOCALVERSION=+ modules_prepare
make -C kernel O="$sdk" LOCALVERSION=+ -j4 M=drivers/soundwire modules
make -C kernel O="$sdk" LOCALVERSION=+ -j4 M=drivers/soc/qcom modules
make -C kernel O="$sdk" LOCALVERSION=+ -j4 \
    KBUILD_EXTRA_SYMBOLS="$PWD/kernel/drivers/soundwire/Module.symvers $PWD/kernel/drivers/soc/qcom/Module.symvers" \
    M=sound modules
mkdir -p out/live-i2c-modules66
cp kernel/drivers/i2c/algos/i2c-algo-bit.c kernel/drivers/i2c/busses/i2c-gpio.c out/live-i2c-modules66/
printf 'obj-m += i2c-algo-bit.o i2c-gpio.o\n' >out/live-i2c-modules66/Makefile
make -C kernel O="$sdk" LOCALVERSION=+ -j4 M="$PWD/out/live-i2c-modules66" modules
mkdir out/live-audio-modules66
python3 - <<'PY'
import hashlib,json,shutil,subprocess
from pathlib import Path
manifest={}
for base in ['kernel/sound','kernel/drivers/soundwire','kernel/drivers/soc/qcom','out/live-i2c-modules66']:
 for path in Path(base).rglob('*.ko'):
  if base.endswith('/qcom') and path.name!='apr.ko':continue
  target=Path('out/live-audio-modules66')/path.name
  assert not target.exists()
  shutil.copy2(path,target)
  vermagic=subprocess.check_output(['modinfo','-F','vermagic',str(path)],text=True).strip()
  assert vermagic=='7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
  undefined=subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(path)],text=True)
  symbols=subprocess.check_output(['aarch64-linux-gnu-nm',str(path)],text=True)
  manifest[path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'vermagic':vermagic,
    'undefined':[s.split()[-1] for s in undefined.splitlines() if s.strip()],
    'exports':[s.split()[-1].removeprefix('__ksymtab_') for s in symbols.splitlines()
       if s.split() and s.split()[-1].startswith('__ksymtab_')]}
available={line.split()[1] for line in Path('out/kernel-live-audio66/vmlinux.symvers').read_text().splitlines()}
for info in manifest.values():available.update(info['exports'])
missing={name:sorted(set(info['undefined'])-available) for name,info in manifest.items()
         if set(info['undefined'])-available}
assert not missing,missing
Path('out/live-audio-modules66/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('All',len(manifest),'modules match this exact kernel and its exported symbols')
PY
tar -C out/live-audio-modules66 -cf out/live-audio-modules66.tar .
