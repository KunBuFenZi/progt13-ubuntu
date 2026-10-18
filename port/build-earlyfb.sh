#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
cp port/early-fb-console.inc kernel/drivers/firmware/efi/tb378fc-earlyfb.inc
python3 - <<'PY'
from pathlib import Path
p = Path('kernel/drivers/firmware/efi/earlycon.c')
line = '\n#include "tb378fc-earlyfb.inc"\n'
if line not in p.read_text():
    with p.open('a') as f:
        f.write(line)
PY
bash port/build-stage1.sh
python3 - <<'PY'
from pathlib import Path
import hashlib, json
p = Path('out/stage1-build.json')
m = json.loads(p.read_text())
m['diagnostic_variant'] = 'inherited UEFI framebuffer early console'
for name in ('port/early-fb-console.inc', 'port/build-earlyfb.sh'):
    b = Path(name).read_bytes()
    m['files'][name] = dict(sha256=hashlib.sha256(b).hexdigest(), size=len(b))
p.write_text(json.dumps(m, indent=2) + '\n')
PY
