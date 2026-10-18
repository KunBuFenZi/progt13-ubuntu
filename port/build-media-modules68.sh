#!/bin/bash
# Only compile the decoder's dependency closure; do not build unrelated TV drivers.
set -euo pipefail
cd "$(dirname -- "$0")/.."
sdk="$PWD/out/kernel-peripherals68"
test "$(cat logs/kernel-peripherals68.exit)" = 0
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
cp "$sdk/vmlinux.symvers" "$sdk/Module.symvers"
dest="$PWD/out/media-modules68"
mkdir -p "$dest"
symbols=()
for path in drivers/media/mc drivers/media/common/videobuf2 drivers/media/v4l2-core drivers/media/platform/qcom/iris; do
    extra="${symbols[*]}"
    make -C kernel O="$sdk" LOCALVERSION=+ -j3 KBUILD_EXTRA_SYMBOLS="$extra" M="$path" modules
    symbols+=("$PWD/kernel/$path/Module.symvers")
    find "kernel/$path" -maxdepth 1 -type f -name '*.ko' -exec cp -t "$dest" -- {} +
done
python3 - <<'PY'
from pathlib import Path
import hashlib,json,subprocess
dest=Path('out/media-modules68')
manifest={}
exports={line.split()[1] for line in Path('out/kernel-peripherals68/vmlinux.symvers').read_text().splitlines()}
for p in dest.glob('*.ko'):
    names=subprocess.check_output(['aarch64-linux-gnu-nm',str(p)],text=True)
    undefined=subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(p)],text=True)
    record={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'vermagic':subprocess.check_output(['modinfo','-F','vermagic',str(p)],text=True).strip(),
            'exports':[s.split()[-1].removeprefix('__ksymtab_') for s in names.splitlines() if s.split() and s.split()[-1].startswith('__ksymtab_')],
            'undefined':[s.split()[-1] for s in undefined.splitlines() if s.split()]}
    manifest[p.name]=record;exports.update(record['exports'])
missing={n:sorted(set(i['undefined'])-exports) for n,i in manifest.items() if set(i['undefined'])-exports}
assert not missing,missing
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('VERIFIED_MODULE_CLOSURE',len(manifest))
PY
