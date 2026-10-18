#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fetch the pinned kernel and apply the exported, device-tested platform diff."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, default=ROOT / 'out/kernel-source')
a = p.parse_args()
lock = json.loads((ROOT / 'kernel/source.json').read_text())
out = a.output.resolve()
if out.exists():
    p.error('Use a new output directory; an existing checkout is never reset')
subprocess.run(['git', 'clone', '--filter=blob:none', '--no-checkout', lock['repository'], str(out)], check=True)
subprocess.run(['git', '-C', str(out), 'checkout', '--detach', lock['commit']], check=True)
for name in lock['patches']:
    patch = ROOT / 'kernel' / name
    subprocess.run(['git', '-C', str(out), 'apply', '--check', str(patch)], check=True)
    subprocess.run(['git', '-C', str(out), 'apply', str(patch)], check=True)
print(out)
