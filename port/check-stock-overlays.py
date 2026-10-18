#!/usr/bin/env python3
"""Apply selected stock overlays with libfdt and check device isolation."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
fdt = runpy.run_path(str(ROOT / 'tools/inspect-stock-inputs.py'))['fdt']
BASE = ROOT / 'out/abl-stage1/erhai-abl.dtb'
SKIP = ('/erhai-abl', '/__symbols__')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, default=BASE)
parser.add_argument('--entry', type=int, action='append', help='Overlay index (default: this unit\'s 64)')
parser.add_argument('--all', action='store_true', help='Slow: apply all 91 overlays')
args = parser.parse_args()
BASE = args.base.resolve()
before = {p: props for p, props in fdt(BASE.read_bytes()).items() if not p.startswith(SKIP)}
selected = list(range(91)) if args.all else (args.entry or [64])
results = []
with tempfile.TemporaryDirectory() as tmp:
    output = Path(tmp) / 'applied.dtb'
    for overlay in sorted((BASE.parent / 'stock-dtbo').glob('entry.*.dtb')):
        if int(overlay.stem.split('.')[1]) not in selected:
            continue
        proc = subprocess.run(['fdtoverlay', '-i', str(BASE), '-o', str(output), str(overlay)],
                              capture_output=True, text=True, timeout=60)
        entry = {'entry': overlay.name, 'apply_exit': proc.returncode}
        if proc.returncode:
            entry['error'] = proc.stderr
        else:
            after = {p: props for p, props in fdt(output.read_bytes()).items() if not p.startswith(SKIP)}
            entry['changed_nodes_outside_sink'] = sorted(p for p in before if before[p] != after.get(p))
            entry['new_nodes_outside_sink'] = sorted(set(after) - set(before))
        entry['passed'] = (proc.returncode == 0 and not entry['changed_nodes_outside_sink']
                           and not entry['new_nodes_outside_sink'])
        results.append(entry)
report = {'passed': len(results) == len(selected) and all(r['passed'] for r in results),
          'note': 'libfdt offline check; ABL uses libufdt and still requires a device test',
          'entries': results}
(BASE.parent / 'overlay-application-check.json').write_text(json.dumps(report, indent=2) + '\n')
print(f'isolated overlays: {sum(r["passed"] for r in results)}/{len(results)}')
raise SystemExit(0 if report['passed'] else 1)
