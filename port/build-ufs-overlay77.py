#!/usr/bin/env python3
"""Compile/check the UFS overlay and activation module without loading either."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inputs', default='out/ufs77b')
parser.add_argument('--output', default='out/ufs77b-overlay-build')
args = parser.parse_args()
src = root / args.inputs
initial = root / 'out/ufs77/mainline-before.dtb'
work = root / args.output
work.mkdir(exist_ok=True)
assert not any(work.iterdir()), 'Refusing to overwrite a previous build'
sdk = root / 'out/kernel-ufs77'
kernel = root / 'kernel'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs = json.loads((src / 'overlay-inputs.json').read_text())
assert sha(initial) == inputs['live_initial_fdt_sha256']
assert sha(src / 'tb378fc-ufs77.dtso') == inputs['dts_sha256']
assert sha(sdk / 'arch/arm64/boot/Image') == '21c91b2dddf71e38ed6ae4366135a56ec9e02fe9d617bba33937b3e40c6483e9'
shutil.copy2(src / 'tb378fc-ufs77.dtso', work)
overlay = work / 'tb378fc-ufs77.dtbo'
merged = work / 'merged-offline.dtb'
subprocess.run(['dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', str(overlay), str(work / 'tb378fc-ufs77.dtso')], check=True)
subprocess.run(['fdtoverlay', '-i', str(initial), '-o', str(merged), str(overlay)], check=True)

def fdt(path):
    b = path.read_bytes()
    magic, total, off, strings, reserve, version, last, cpu, slen, dlen = struct.unpack_from('>10I', b)
    assert magic == 0xd00dfeed and total == len(b)
    stack = []; nodes = {}
    while True:
        token, = struct.unpack_from('>I', b, off); off += 4
        if token == 1:
            end = b.index(0, off); name = b[off:end].decode()
            stack.append(name); off = (end + 4) & ~3
            nodes['/' + '/'.join(stack[1:])] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, nameoff = struct.unpack_from('>II', b, off); off += 8
            start = strings + nameoff; end = b.index(0, start)
            nodes['/' + '/'.join(stack[1:])][b[start:end].decode()] = b[off:off+size].hex()
            off = (off + size + 3) & ~3
        elif token == 4:
            continue
        else:
            assert token == 9
            return nodes

before, after = fdt(initial), fdt(merged)
rsc = '/soc@0/rsc@16500000'
hc, phy = '/soc@0/ufs@1d84000', '/soc@0/phy@1d80000'
allowed = {hc: {'reset-gpios', 'vcc-supply', 'vcc-max-microamp', 'vccq-supply', 'vccq-max-microamp', 'status'},
           phy: {'vdda-phy-supply', 'vdda-pll-supply', 'status'},
           '/__symbols__': {'ufs77_bob2', 'ufs77_l17b', 'ufs77_l1d', 'ufs77_l1j'}}
changes = {}
for path, props in before.items():
    assert path in after
    changed = {key for key in props.keys() | after[path].keys() if props.get(key) != after[path].get(key)}
    if changed:
        assert path in allowed and changed <= allowed[path], (path, changed)
        changes[path] = sorted(changed)
added = set(after) - set(before)
expected = {rsc + '/ufs77-regulators-' + p + suffix for p, suffixes in
            [('b', ['', '/bob2', '/ldo17']), ('d', ['', '/ldo1']), ('j', ['', '/ldo1'])] for suffix in suffixes}
assert added == expected, added ^ expected
cell = lambda x: struct.pack('>I', x).hex()
links = {(hc, 'vcc-supply'): rsc + '/ufs77-regulators-b/ldo17',
         (hc, 'vccq-supply'): rsc + '/ufs77-regulators-d/ldo1',
         (phy, 'vdda-phy-supply'): rsc + '/ufs77-regulators-j/ldo1',
         (rsc + '/ufs77-regulators-b', 'vdd-l17-supply'): rsc + '/ufs77-regulators-b/bob2'}
for (path, key), target in links.items():
    assert after[path][key] == after[target]['phandle'], (path, key)
for path, key, value in [(hc, 'vcc-max-microamp', 1300000), (hc, 'vccq-max-microamp', 1200000),
                         (phy, 'vdda-pll-supply', 142), (rsc + '/ufs77-regulators-b', 'vdd-bob2-supply', 285),
                         (rsc + '/ufs77-regulators-d', 'vdd-l1-supply', 289),
                         (rsc + '/ufs77-regulators-j', 'vdd-l1-supply', 288)]:
    assert after[path][key] == cell(value)
assert after[hc]['reset-gpios'] == cell(55) + cell(215) + cell(1)
assert all(after[p]['status'] == b'okay\0'.hex() for p in [hc, phy])
assert all(after[rsc + '/ufs77-regulators-b/bob2'][p] == cell(3000000)
           for p in ['regulator-min-microvolt', 'regulator-max-microvolt'])

shutil.copy2(root / 'port/live-ufs-overlay77.c', work)
(work / 'Makefile').write_text('obj-m += live-ufs-overlay77.o\n')
subprocess.run(['make', '-C', str(kernel), 'O=' + str(sdk), 'LOCALVERSION=+', '-j2',
                'M=' + str(work), 'modules'], check=True,
               env=dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-'))
module = work / 'live-ufs-overlay77.ko'
imports = {l.split()[-1] for l in subprocess.check_output(['aarch64-linux-gnu-nm', '-u', str(module)], text=True).splitlines()}
exports = {l.split()[1] for l in (sdk / 'vmlinux.symvers').read_text().splitlines()}
assert not imports - exports, imports - exports
vermagic = subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip()
assert vermagic == '7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
record = {'status': 'BUILT_VERIFIED_NOT_LOADED', 'overlay_sha256': sha(overlay),
          'module_sha256': sha(module), 'source_sha256': sha(work / 'live-ufs-overlay77.c'),
          'vermagic': vermagic, 'imports': sorted(imports), 'changed_existing_nodes': changes,
          'added_nodes': sorted(added), 'offline_merge_sha256': sha(merged),
          'inputs': inputs, 'lifetime': 'resident until next reboot; no live HBA teardown'}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: v for k, v in record.items() if k not in ['imports', 'inputs']}, indent=2))
