#!/bin/bash
set -euo pipefail
cd "$(dirname -- "$0")/.."
tag="${1:?Provide a unique artifact tag}"
[[ "$tag" =~ ^[a-z0-9]+$ ]]
trap 'echo $? > "logs/build-live-amp-$tag.exit"' EXIT
test ! -e "out/live-audio-$tag"
cmp out/kernel-memory/.config out/kernel-live-audio66/.config
cp port/aw88480.c kernel/sound/soc/codecs/aw88480.c
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
make -C kernel O="$PWD/out/kernel-memory" LOCALVERSION=+ -j4 \
 KBUILD_EXTRA_SYMBOLS="$PWD/kernel/drivers/soundwire/Module.symvers $PWD/kernel/drivers/soc/qcom/Module.symvers" \
 M=sound modules
python3 - "$tag" <<'PY'
import hashlib,json,re,shutil,subprocess,sys
from pathlib import Path
tag=sys.argv[1]
dest=Path('out')/('live-audio-'+tag)
shutil.copytree('out/live-audio-modules66',dest)
name='snd-soc-aw88480.ko'
module=dest/name
shutil.copy2('kernel/sound/soc/codecs/'+name,module)
source=Path('port/aw88480.c')
shutil.copy2(source,dest/'source-aw88480.c')
manifest=json.loads((dest/'manifest.json').read_text())
old_hash=manifest[name]['sha256']
info=manifest[name]
info['sha256']=hashlib.sha256(module.read_bytes()).hexdigest()
info['vermagic']=subprocess.check_output(['modinfo','-F','vermagic',str(module)],text=True).strip()
assert info['vermagic']=='7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
info['undefined']=[s.split()[-1] for s in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(module)],text=True).splitlines() if s.strip()]
info['exports']=[s.split()[-1].removeprefix('__ksymtab_') for s in subprocess.check_output(['aarch64-linux-gnu-nm',str(module)],text=True).splitlines() if s.split() and s.split()[-1].startswith('__ksymtab_')]
available={line.split()[1] for line in Path('out/kernel-live-audio66/vmlinux.symvers').read_text().splitlines()}
for entry in manifest.values():available.update(entry['exports'])
assert not set(info['undefined'])-available
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
gain=lambda name:int(re.search(r'#define AW48_GAIN_'+name+r'\s+(\d+)',source.read_text())[1])
proof={'kernel_image_sha256':hashlib.sha256(Path('out/kernel-live-audio66/arch/arm64/boot/Image').read_bytes()).hexdigest(),
       'old_module_sha256':old_hash,'module':info,
       'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
       'initial_attenuation_below_native_db':(511-gain('DEFAULT'))/4,
       'maximum_gain_below_native_db':(511-gain('MAX'))/4,
       'status':'COMPILED_NOT_DEVICE_TESTED'}
Path('out',f'live-amp-{tag}-build.json').write_text(json.dumps(proof,indent=2)+'\n')
PY
tar -C "out/live-audio-$tag" -cf "out/live-audio-$tag.tar" .
