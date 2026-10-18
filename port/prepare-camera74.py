#!/usr/bin/env python3
"""Prepare a complete static camera DT, with native rails and wiring."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume', action='store_true')
args = parser.parse_args()
work = root / 'out/camera-tree74'; work.mkdir(exist_ok=args.resume)
base = root / 'out/microphone-tree73/sm8750-lenovo-tb378fc-microphone73.dtb'
reference = root / 'reference/camera74/h0cheung-kernel/arch/arm64/boot/dts/qcom/sm8750.dtsi'
assert hashlib.sha256(reference.read_bytes()).hexdigest() == next(x['sha256'] for x in json.loads((root / 'reference/camera74/h0cheung-kernel/source-verified.json').read_text())['files'] if x['path'].endswith('/sm8750.dtsi'))

def parse(data):
    _, _, pos, strings = struct.unpack_from('>4I', data)
    nodes, stack = {}, []
    while True:
        token, = struct.unpack_from('>I', data, pos); pos += 4
        if token == 1:
            end = data.index(0, pos); stack.append(data[pos:end].decode()); pos = (end + 4) & ~3
            nodes['/' + '/'.join(filter(None, stack))] = {}
        elif token == 2: stack.pop()
        elif token == 3:
            length, offset = struct.unpack_from('>II', data, pos); pos += 8
            end = data.index(0, strings + offset); name = data[strings + offset:end].decode()
            nodes['/' + '/'.join(filter(None, stack))][name] = data[pos:pos + length]; pos = (pos + length + 3) & ~3
        elif token == 9: return nodes
        else: assert token == 4

original = parse(base.read_bytes())
assert not any('cci@' in name or 'isp@ad27000' in name for name in original)
native = json.loads((root / 'out/native-camera-flash69.json').read_text())
rear, front = native
assert rear['props']['csiphy-sd-index']['cells'] == [5]
assert front['props']['csiphy-sd-index']['cells'] == [1]
assert rear['props']['rgltr-min-voltage']['cells'][:4] == [1800000, 2800000, 1200000, 2800000]
assert front['props']['rgltr-min-voltage']['cells'][:3] == [1800000, 2800000, 1200000]
symbols = {'camcc': '/soc@0/clock-controller@ade0000', 'cambistmclkcc': '/soc@0/clock-controller@1760000',
           'gcc': '/soc@0/clock-controller@100000', 'apps_smmu': '/soc@0/iommu@15000000',
           'gem_noc': '/soc@0/interconnect@24100000', 'config_noc': '/soc@0/interconnect@1600000',
           'mmss_noc': '/soc@0/interconnect@1780000', 'mc_virt': '/interconnect-1',
           'tlmm': '/soc@0/pinctrl@f100000'}
seed = work / 'base-with-camera-phandles.dtb'; shutil.copy2(base, seed)
maxhandle = max(struct.unpack('>I', props['phandle'])[0] for props in original.values() if 'phandle' in props)
handles = {}; assigned = []
for name, path in symbols.items():
    assert path in original, path
    if 'phandle' in original[path]: value, = struct.unpack('>I', original[path]['phandle'])
    else:
        maxhandle += 1; value = maxhandle
        subprocess.run(['fdtput', '-t', 'x', str(seed), path, 'phandle', format(value, 'x')], check=True)
        assigned.append([path, 'phandle'])
    handles[name] = value

def find_reg(name):
    found = [(p, v) for p, v in original.items() if v.get('regulator-name') == name.encode() + b'\0']
    assert len(found) == 1, name
    return struct.unpack('>I', found[0][1]['phandle'])[0]

vph = find_reg('vph_pwr'); bob = find_reg('vreg_bob1')
s3g = find_reg('vreg_s3g'); s7i = find_reg('vreg_s7i_usb_supply')
phy09 = find_reg('tb378fc-pcie-phy'); phy12 = find_reg('vreg_l3g_usb_hsphy')

text = reference.read_text()
def block(label):
    match = re.search(r'\b' + label + r':\s*[^\n{]+\{', text)
    assert match
    start = match.start(); pos = match.end(); depth = 1
    while depth:
        if text[pos] == '{': depth += 1
        elif text[pos] == '}': depth -= 1
        pos += 1
    return text[start:pos + 1]

camss = block('camss').replace('status = "disabled";', 'status = "okay";')
rails = '\n'.join(f'vdd-csiphy{i}-0p9-supply = <{phy09}>; vdd-csiphy{i}-1p2-supply = <{phy12}>;' for i in range(6))
camss = camss.replace('compatible = "qcom,sm8750-camss";', 'compatible = "qcom,sm8750-camss";\n' + rails)
camss = camss.replace('#size-cells = <0>;', '''#size-cells = <0>;
    port@1 { reg = <1>; camera74_front_phy: endpoint { data-lanes = <0 1 2 3>; remote-endpoint = <&camera74_front_out>; }; };
    port@5 { reg = <5>; camera74_rear_phy: endpoint { data-lanes = <0 1 2 3>; remote-endpoint = <&camera74_rear_out>; }; };''')

def cci(index, sensor):
    value = block('cci' + str(index))
    value = value.replace('status = "disabled";', 'status = "okay";', 1)
    pin = f'pinctrl-names = "default"; pinctrl-0 = <&camera74_cci{index}>;'
    value = value.replace('#address-cells = <1>;', pin + '\n#address-cells = <1>;', 1)
    key = '\t\t\t\t#size-cells = <0>;'
    assert value.count(key) == 2
    value = value.replace(key, key + '\n' + sensor, 1)
    return value

rear_sensor = '''camera74_rear: camera@36 {
    compatible = "lenovo,tb378fc-ov13b10", "ovti,ov13b10";
    reg = <0x36>;
    clocks = <&cambistmclkcc CAM_BIST_MCLK_CC_MCLK3_CLK>;
    assigned-clocks = <&cambistmclkcc CAM_BIST_MCLK_CC_MCLK3_CLK>;
    assigned-clock-rates = <19200000>;
    power-domains = <&camcc CAM_CC_TITAN_TOP_GDSC>;
    reset-gpios = <&tlmm 11 GPIO_ACTIVE_LOW>;
    pinctrl-names = "default"; pinctrl-0 = <&camera74_rear_pins>;
    dovdd-supply = <&camera74_vio>; avdd-supply = <&camera74_rear_avdd>;
    dvdd-supply = <&camera74_rear_dvdd>; vaf-supply = <&camera74_vaf>;
    orientation = <1>; rotation = <90>;
    port { camera74_rear_out: endpoint {
        data-lanes = <1 2 3 4>; link-frequencies = /bits/ 64 <560000000>;
        remote-endpoint = <&camera74_rear_phy>;
    }; };
};'''
front_sensor = '''camera74_front: camera@31 {
    compatible = "galaxycore,gc08a8"; reg = <0x31>;
    clocks = <&cambistmclkcc CAM_BIST_MCLK_CC_MCLK4_CLK>;
    assigned-clocks = <&cambistmclkcc CAM_BIST_MCLK_CC_MCLK4_CLK>;
    assigned-clock-rates = <19200000>;
    power-domains = <&camcc CAM_CC_TITAN_TOP_GDSC>;
    reset-gpios = <&tlmm 7 GPIO_ACTIVE_LOW>;
    pinctrl-names = "default"; pinctrl-0 = <&camera74_front_pins>;
    dovdd-supply = <&camera74_vio>; avdd-supply = <&camera74_front_avdd>;
    dvdd-supply = <&camera74_front_dvdd>;
    orientation = <0>; rotation = <270>;
    port { camera74_front_out: endpoint {
        data-lanes = <1 2 3 4>; link-frequencies = /bits/ 64 <336000000>;
        remote-endpoint = <&camera74_front_phy>;
    }; };
};'''

def regulator(label, number, voltage):
    return f'''{label}: ldo{number} {{ regulator-name = "tb378fc-camera-{label}";
        regulator-min-microvolt = <{voltage}>; regulator-max-microvolt = <{voltage}>;
        regulator-initial-mode = <RPMH_REGULATOR_MODE_HPM>;
        regulator-allow-set-load; }};'''

source = '''// SPDX-License-Identifier: BSD-3-Clause
/dts-v1/;
/plugin/;
#include <dt-bindings/clock/qcom,sm8750-camcc.h>
#include <dt-bindings/clock/qcom,sm8750-cambistmclkcc.h>
#include <dt-bindings/clock/qcom,sm8750-gcc.h>
#include <dt-bindings/interconnect/qcom,sm8750-rpmh.h>
#include <dt-bindings/interconnect/qcom,icc.h>
#include <dt-bindings/interrupt-controller/arm-gic.h>
#include <dt-bindings/gpio/gpio.h>
#include <dt-bindings/regulator/qcom,rpmh-regulator.h>
/ {
'''
source += f'''fragment@0 {{ target-path = "/soc@0"; __overlay__ {{
    #address-cells = <2>; #size-cells = <2>;
    {cci(0, rear_sensor)}
    {cci(1, front_sensor)}
    {camss}
}}; }};
fragment@1 {{ target-path = "/soc@0/rsc@16500000/regulators-b"; __overlay__ {{
    vdd-l1-l4-l10-supply = <{s3g}>;
    vdd-l6-l7-supply = <{bob}>; vdd-l8-l9-supply = <{bob}>;
    vdd-l11-supply = <{s7i}>;
    {regulator('camera74_front_avdd', 7, 2800000)}
    {regulator('camera74_rear_avdd', 8, 2800000)}
    {regulator('camera74_vio', 10, 1800000)}
    {regulator('camera74_rear_dvdd', 11, 1200000)}
    {regulator('camera74_vaf', 16, 2800000)}
}}; }};
fragment@2 {{ target-path = "/soc@0/rsc@16500000/regulators-i"; __overlay__ {{
    vdd-l1-supply = <{s7i}>;
    {regulator('camera74_front_dvdd', 1, 1200000)}
}}; }};
fragment@3 {{ target-path = "/soc@0/pinctrl@f100000"; __overlay__ {{
    camera74_cci0: tb378fc-camera74-cci0 {{
        sda-pins {{ pins = "gpio113"; function = "cci_i2c_sda"; drive-strength = <2>; bias-pull-up; }};
        scl-pins {{ pins = "gpio114"; function = "cci_i2c_scl"; drive-strength = <2>; bias-pull-up; }};
    }};
    camera74_cci1: tb378fc-camera74-cci1 {{
        sda-pins {{ pins = "gpio117"; function = "cci_i2c_sda"; drive-strength = <2>; bias-pull-up; }};
        scl-pins {{ pins = "gpio118"; function = "cci_i2c_scl"; drive-strength = <2>; bias-pull-up; }};
    }};
    camera74_rear_pins: tb378fc-camera74-rear {{
        mclk-pins {{ pins = "gpio92"; function = "cam_mclk"; drive-strength = <2>; bias-disable; }};
        reset-pins {{ pins = "gpio11"; function = "gpio"; drive-strength = <2>; bias-disable; }};
    }};
    camera74_front_pins: tb378fc-camera74-front {{
        mclk-pins {{ pins = "gpio93"; function = "cam_aon_mclk4"; drive-strength = <2>; bias-disable; }};
        reset-pins {{ pins = "gpio7"; function = "gpio"; drive-strength = <2>; bias-disable; }};
    }};
}}; }};
}};
'''
for name, value in handles.items(): source = re.sub(r'&' + name + r'\b', str(value), source)
dtso = work / 'tb378fc-camera74.dtso'; dtso.write_text(source)
preprocessed = work / 'tb378fc-camera74.dts'
with preprocessed.open('w') as output:
    subprocess.run(['aarch64-linux-gnu-gcc', '-E', '-P', '-nostdinc', '-undef', '-D__DTS__', '-x', 'assembler-with-cpp',
                    '-I', str(root / 'kernel/include'), str(dtso)], stdout=output, check=True)
dtbo = work / 'tb378fc-camera74.dtbo'
subprocess.run(['dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', str(dtbo), str(preprocessed)], check=True)
dtb = work / 'sm8750-lenovo-tb378fc-camera74.dtb'
subprocess.run(['fdtoverlay', '-i', str(seed), '-o', str(dtb), str(dtbo)], check=True)
after = parse(dtb.read_bytes())
delta = [(path, name) for path in after for name, value in after[path].items() if original.get(path, {}).get(name) != value]
allowed_prefix = ('/soc@0/cci@ac7b000', '/soc@0/cci@ac7c000', '/soc@0/isp@ad27000',
                  '/soc@0/rsc@16500000/regulators-b', '/soc@0/rsc@16500000/regulators-i',
                  '/soc@0/pinctrl@f100000/tb378fc-camera74-', '/__symbols__')
assert all(path.startswith(allowed_prefix) or [path, name] in assigned for path, name in delta), delta
assert all(after.get(path, {}).get(name) == value for path, props in original.items() for name, value in props.items())
phandles = {}
for path, props in after.items():
    if 'phandle' in props:
        handle, = struct.unpack('>I', props['phandle']); assert handle not in phandles
        phandles[handle] = path
for bus, sensor in [(0, 'camera@36'), (1, 'camera@31')]:
    props = after[f'/soc@0/cci@ac7{11 + bus:x}000/i2c-bus@0/{sensor}']
    for key in ['clocks', 'power-domains', 'dovdd-supply', 'avdd-supply', 'dvdd-supply']:
        assert struct.unpack_from('>I', props[key])[0] in phandles
record = {'status': 'STATIC_CAMERA74_TREE_PREPARED_NOT_BOOTED', 'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
          'dtb_sha256': hashlib.sha256(dtb.read_bytes()).hexdigest(), 'changed_properties': delta,
          'assigned_camera_clock_phandles': assigned, 'native_csiphy': {'front': 1, 'rear': 5},
          'new_camera_regulators': 6, 'existing_display_touch_usb_wifi_audio_properties_preserved': True,
          'needs_complete_static_boot': True, 'remaining': ['Sensor identity probe', 'Frame capture', 'Lens and flash integration']}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: v for k, v in record.items() if k != 'changed_properties'}, indent=2))
