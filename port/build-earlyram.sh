#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
src="$root/kernel"
out="$root/out/kernel-stage1"
cd "$root"
# Keep the tested baseline components before changing this build directory.
mkdir -p out/kernel-stage1-before-earlyram
for item in arch/arm64/boot/Image .config; do
    target="out/kernel-stage1-before-earlyram/$(basename "$item")"
    test -e "$target" || cp "$out/$item" "$target"
done
cp port/early-ram-console.c "$src/drivers/tty/serial/tb378fc-earlyram.c"
python3 - "$src" <<'PY'
from pathlib import Path
import sys
serial = Path(sys.argv[1]) / 'drivers/tty/serial'
kconfig = serial / 'Kconfig'
if 'config TB378FC_EARLY_RAM_CONSOLE' not in kconfig.read_text():
    with kconfig.open('a') as f:
        f.write('\nconfig TB378FC_EARLY_RAM_CONSOLE\n'
                '\tbool "TB378FC temporary persistent early console"\n'
                '\tdepends on SERIAL_EARLYCON && !PSTORE_RAM\n')
makefile = serial / 'Makefile'
line = 'obj-$(CONFIG_TB378FC_EARLY_RAM_CONSOLE) += tb378fc-earlyram.o\n'
if line not in makefile.read_text():
    with makefile.open('a') as f:
        f.write('\n' + line)
PY
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
export KBUILD_BUILD_USER=tb378fc KBUILD_BUILD_HOST=build-host
export KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 UTC' KBUILD_BUILD_VERSION=1
"$src/scripts/kconfig/merge_config.sh" -m -O "$out" "$out/.config" port/earlyram.config
make -C "$src" O="$out" olddefconfig
grep -Fxq CONFIG_TB378FC_EARLY_RAM_CONSOLE=y "$out/.config"
grep -Fxq '# CONFIG_PSTORE_RAM is not set' "$out/.config"
make -C "$src" O="$out" -j4 Image
python3 - "$root" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
path = root / 'out/stage1-build.json'
manifest = json.loads(path.read_text())
manifest['diagnostic_variant'] = 'early RAM console; normal ramoops driver disabled'
for name in ('out/kernel-stage1/arch/arm64/boot/Image', 'out/kernel-stage1/.config',
             'port/early-ram-console.c', 'port/earlyram.config', 'port/build-earlyram.sh'):
    p = root / name
    manifest['files'][name] = dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), size=p.stat().st_size)
path.write_text(json.dumps(manifest, indent=2) + '\n')
print('EARLY_RAM_KERNEL_BUILD_PASSED')
PY
