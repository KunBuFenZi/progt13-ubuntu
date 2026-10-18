#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
python3 port/enable-probe-trace.py
bash port/build-earlyfb.sh
git -C kernel diff -- drivers/base/dd.c drivers/base/core.c >out/probe-trace.patch
python3 - <<'PY'
from pathlib import Path
import hashlib, json
p = Path('out/stage1-build.json')
m = json.loads(p.read_text())
m['diagnostic_variant'] = 'large early framebuffer with probe/sync/deferred-work tracing'
for name in ('port/enable-probe-trace.py', 'port/build-probe-trace.sh',
             'kernel/drivers/base/dd.c', 'kernel/drivers/base/core.c', 'out/probe-trace.patch'):
    b = Path(name).read_bytes()
    m['files'][name] = dict(sha256=hashlib.sha256(b).hexdigest(), size=len(b))
p.write_text(json.dumps(m, indent=2) + '\n')
PY
