#!/usr/bin/env python3
"""Extend the accepted binary DT with this unit's USB-C/DP wiring only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', default='out/usbc-tree70')
parser.add_argument('--negotiated-current', action='store_true')
args = parser.parse_args()
work = (root / args.output).resolve()
assert work.parent == root / 'out' and work.name.startswith('usbc-tree70')
work.mkdir(exist_ok=False)
base = root / 'out/peripherals-tree68/sm8750-lenovo-tb378fc-peripherals.dtb'
tree = work / 'sm8750-lenovo-tb378fc-usbc70.dtb'
shutil.copy2(base, tree)

def parse(data):
    magic, total, pos, strings = struct.unpack_from('>4I', data)
    assert magic == 0xd00dfeed and total == len(data)
    nodes, stack = {}, []
    while True:
        token, = struct.unpack_from('>I', data, pos); pos += 4
        if token == 1:
            end = data.index(0, pos)
            stack.append(data[pos:end].decode()); pos = (end + 4) & ~3
            path = '/' + '/'.join(filter(None, stack)); nodes[path] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from('>II', data, pos); pos += 8
            end = data.index(0, strings + nameoff)
            name = data[strings + nameoff:end].decode()
            nodes['/' + '/'.join(filter(None, stack))][name] = data[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == 9:
            break
        else:
            assert token == 4
    return nodes

before = parse(base.read_bytes())
nodes = {p: dict(props) for p, props in before.items()}
changes = set()
ids = [struct.unpack('>I', p['phandle'])[0] for p in nodes.values() if 'phandle' in p]
next_id = max(ids) + 1

def textval(path, name):
    return nodes[path][name].rstrip(b'\0').decode()

def run(*args):
    return subprocess.check_output([str(a) for a in args], text=True).strip()

def ensure(path):
    if path in nodes:
        return
    ensure(path.rsplit('/', 1)[0] or '/')
    run('fdtput', '-c', tree, path)
    nodes[path] = {}

def put(path, prop, kind=None, *values):
    ensure(path)
    if kind:
        run('fdtput', '-t', kind, tree, path, prop, *values)
        value = (b''.join(str(v).encode() + b'\0' for v in values) if kind == 's'
                 else b''.join(struct.pack('>I', int(v)) for v in values))
    else:
        run('fdtput', tree, path, prop)
        value = b''
    nodes[path][prop] = value
    changes.add((path, prop))

def handle(path):
    global next_id
    ensure(path)
    if 'phandle' not in nodes[path]:
        put(path, 'phandle', 'i', next_id); next_id += 1
    return struct.unpack('>I', nodes[path]['phandle'])[0]

def regulator(name):
    found = [p for p in nodes if nodes[p].get('regulator-name') == name.encode() + b'\0']
    assert len(found) == 1, (name, found)
    return handle(found[0])

pairs = []
def link(a, b):
    put(a, 'remote-endpoint', 'i', handle(b))
    put(b, 'remote-endpoint', 'i', handle(a))
    pairs.append((a, b))

def ports(parent, count):
    put(parent + '/ports', '#address-cells', 'i', 1)
    put(parent + '/ports', '#size-cells', 'i', 0)
    for port in range(count):
        put(parent + '/ports/port@' + str(port), 'reg', 'i', port)

usb = '/soc@0/usb@a600000'
phy = '/soc@0/phy@88e8000'
i2c = '/soc@0/geniqup@ac0000/i2c@a8c000'
dp = '/soc@0/display-subsystem@ae00000/displayport-controller@af54000'
connector = '/pmic-glink/connector@0'
mux = i2c + '/typec-mux@e'
assert textval(usb, 'maximum-speed') == 'high-speed'
assert textval(usb, 'dr_mode') == 'peripheral'
assert textval(phy, 'compatible') == 'qcom,sm8750-qmp-usb3-dp-phy'
assert textval(dp, 'status') == 'disabled'
assert mux not in nodes
hsphy, = struct.unpack('>I', nodes[usb]['phys'])

put('/pmic-glink', '#address-cells', 'i', 1)
put('/pmic-glink', '#size-cells', 'i', 0)
put(connector, 'compatible', 's', 'usb-c-connector')
put(connector, 'reg', 'i', 0)
put(connector, 'power-role', 's', 'dual')
put(connector, 'data-role', 's', 'dual')
ports(connector, 3)

put(i2c, 'status', 's', 'okay')
put(mux, 'compatible', 's', 'qcom,wcd9390-usbss')
put(mux, 'reg', 'i', 14)
put(mux, 'vdd-supply', 'i', regulator('vreg_l15b_usb_repeater'))
put(mux, 'mode-switch')
put(mux, 'orientation-switch')
ports(mux, 1)
put(phy, 'status', 's', 'okay')
put(phy, 'vdda-phy-supply', 'i', regulator('vreg_l3g_usb_hsphy'))
put(phy, 'vdda-pll-supply', 'i', regulator('vreg_l2d_usb_hsphy'))
put(usb, 'phys', 'i', hsphy, handle(phy), 0)
put(usb, 'phy-names', 's', 'usb2-phy', 'usb3-phy')
put(usb, 'maximum-speed', 's', 'super-speed-plus')
put(usb, 'dr_mode', 's', 'otg')
put(usb, 'usb-role-switch')
if args.negotiated_current:
    put(usb, 'usb-psy-name', 's', 'qcom-battmgr-usb')
link(connector + '/ports/port@0/endpoint', usb + '/ports/port@0/endpoint')
link(connector + '/ports/port@1/endpoint', phy + '/ports/port@0/endpoint')
link(connector + '/ports/port@2/endpoint', mux + '/ports/port@0/endpoint')
link(usb + '/ports/port@1/endpoint', phy + '/ports/port@1/endpoint')
link(dp + '/ports/port@1/endpoint', phy + '/ports/port@2/endpoint')
put(dp, 'status', 's', 'okay')

after = parse(tree.read_bytes())
actual = {(p, k) for p in set(before) | set(after) for k in set(before.get(p, {})) | set(after.get(p, {}))
          if before.get(p, {}).get(k) != after.get(p, {}).get(k)}
assert actual <= changes, actual - changes
assert before.keys() <= after.keys()
for a, b in pairs:
    assert after[a]['remote-endpoint'] == after[b]['phandle']
    assert after[b]['remote-endpoint'] == after[a]['phandle']
for p in before:
    if any(x in p for x in ['dsi@', 'panel@', 'spi@', 'serial@898000', 'video-codec@']):
        assert before[p] == after[p], p
(work / 'candidate.dts').write_text(run('dtc', '-q', '-I', 'dtb', '-O', 'dts', tree) + '\n')
record = {'status': 'OFFLINE_NATIVE_USB_C_TREE_NOT_BOOTED',
          'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
          'dtb_sha256': hashlib.sha256(tree.read_bytes()).hexdigest(),
          'changed_properties': [dict(path=p, property=k) for p, k in sorted(actual)],
          'native_aux_switch': 'WCD939x, I2C engine0xa8c000/address0x0e/1.8V L15B',
          'negotiated_current_path': args.negotiated_current,
          'inactive_redriver': 'Native redriver@1c is disabled and unbound; not enabled',
          'graph_pairs': pairs, 'power_policy': 'UCSI/charger firmware controls VBUS; no forced power role',
          'unchanged': ['DSI/panel/120Hz', 'Touch', 'BT UART', 'Iris video'],
          'required_acceptance': ['Boot and USB recovery', 'USB3 enumeration and Wi-Fi SSH',
                                  'USB host keyboard/mouse', 'DP alt mode/HDMI/EDID/hotplug',
                                  'Both cable orientations and charging coexistence']}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: v for k, v in record.items() if k != 'changed_properties'}, indent=2))
