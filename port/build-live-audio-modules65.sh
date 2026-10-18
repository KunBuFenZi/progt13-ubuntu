#!/bin/bash
# Build additive sound modules for the running frozen baseline; never build/boot an Image.
set -euo pipefail
cd "$(dirname -- "$0")/.."
trap 'echo $? > logs/build-live-audio-modules65.exit' EXIT
test ! -e out/module-audio-sdk65
cp -a out/module-sdk65 out/module-audio-sdk65
sdk="$PWD/out/module-audio-sdk65"
kernel/scripts/config --file "$sdk/.config" \
    -m SOUND -m SND -m SND_SOC -m SND_SOC_QCOM -m SND_SOC_QDSP6 \
    -m SND_SOC_SC8280XP -m SND_SOC_AW88480 -m SOUNDWIRE
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
make -C kernel O="$sdk" LOCALVERSION=+ olddefconfig modules_prepare
python3 - <<'PY'
import json,re
from pathlib import Path
def config(path):
 return dict(re.findall(r'^(CONFIG_\w+)=(.*)$', Path(path).read_text(), re.M))
old=config('out/module-sdk65/.config');new=config('out/module-audio-sdk65/.config')
changed={k:{'before':old.get(k,'n'),'after':v} for k,v in new.items() if old.get(k)!=v}
removed={k:v for k,v in old.items() if k not in new}
assert not removed, removed
assert all(v['before']=='n' for v in changed.values()), changed
assert all(k.startswith(('CONFIG_SND','CONFIG_SOUND')) for k in changed), changed
Path('out/live-audio-config-delta65.json').write_text(json.dumps(changed,indent=2)+'\n')
print('Additive sound-only configuration:', len(changed))
PY
make -C kernel O="$sdk" LOCALVERSION=+ KBUILD_MODPOST_WARN=1 -j4 M=drivers/soundwire modules
make -C kernel O="$sdk" LOCALVERSION=+ KBUILD_MODPOST_WARN=1 -j4 M=drivers/soc/qcom modules
make -C kernel O="$sdk" LOCALVERSION=+ KBUILD_MODPOST_WARN=1 -j4 \
    KBUILD_EXTRA_SYMBOLS="$PWD/kernel/drivers/soundwire/Module.symvers $PWD/kernel/drivers/soc/qcom/Module.symvers" \
    M=sound modules
mkdir -p out/live-audio-modules65
python3 - <<'PY'
import hashlib,json,shutil,subprocess
from pathlib import Path
manifest={}
for base in ['kernel/sound','kernel/drivers/soundwire','kernel/drivers/soc/qcom']:
 for path in Path(base).rglob('*.ko'):
  if base.endswith('/qcom') and path.name!='apr.ko': continue
  target=Path('out/live-audio-modules65')/path.name
  assert not target.exists(), target
  shutil.copy2(path,target)
  vermagic=subprocess.check_output(['modinfo','-F','vermagic',str(path)],text=True).strip()
  assert vermagic=='7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64',vermagic
  undefined=subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(path)],text=True)
  exported=subprocess.check_output(['aarch64-linux-gnu-nm',str(path)],text=True)
  manifest[path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
    'vermagic':vermagic,'undefined':[s.split()[-1] for s in undefined.splitlines() if s.strip()],
    'exports':[s.split()[-1].removeprefix('__ksymtab_') for s in exported.splitlines()
               if s.split() and s.split()[-1].startswith('__ksymtab_')]}
Path('out/live-audio-modules65/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Built',len(manifest),'modules; actual running exports must be checked before loading')
PY
