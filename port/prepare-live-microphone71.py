#!/usr/bin/env python3
"""Prepare only the native codec/SoundWire foundation; leave the speaker card intact."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
work = root/'out/microphone-foundation71'
work.mkdir(exist_ok=False)
base = root/'out/usbc-tree70b/sm8750-lenovo-tb378fc-usbc70.dtb'
def parse(data):
    magic,total,pos,strings = struct.unpack_from('>4I',data)
    assert magic==0xd00dfeed and total==len(data)
    nodes,stack = {},[]
    while True:
        token, = struct.unpack_from('>I',data,pos);pos+=4
        if token==1:
            end=data.index(0,pos);stack.append(data[pos:end].decode());pos=(end+4)&~3
            nodes['/'+'/'.join(filter(None,stack))]={}
        elif token==2: stack.pop()
        elif token==3:
            length,offset=struct.unpack_from('>II',data,pos);pos+=8
            end=data.index(0,strings+offset);name=data[strings+offset:end].decode()
            nodes['/'+'/'.join(filter(None,stack))][name]=data[pos:pos+length];pos=(pos+length+3)&~3
        elif token==9: break
        else: assert token==4
    return nodes
before = parse(base.read_bytes())
cell = lambda data: struct.unpack('>I',data)[0]
def regulator(name):
    matches=[(path,props) for path,props in before.items() if props.get('regulator-name')==name.encode()+b'\0']
    assert len(matches)==1,name
    path,props=matches[0]
    return path,cell(props['phandle']),cell(props['regulator-min-microvolt']),cell(props['regulator-max-microvolt'])
rail,rail_id,minimum,maximum = regulator('vreg_l15b_usb_repeater')
assert minimum==maximum==1800000
bob,bob_id,minimum,maximum = regulator('vreg_bob1')
assert minimum<=3296000<=maximum
tlmm = cell(before['/soc@0/pinctrl@f100000']['phandle'])
assert tlmm==0x37
for path in ['/soc@0/soundwire@6ad0000','/soc@0/soundwire@7630000']:
    assert before[path]['status']==b'disabled\0'
native = json.loads((root/'out/native-microphone69.json').read_text())
codec = next(node for node in native if node['path'].endswith('/wcd939x-codec'))['props']
assert codec['qcom,cdc-vdd-px-voltage']['cells']==[1800000,1800000]
assert all(codec['qcom,cdc-micbias'+str(i)+'-mv']['cells']==[1800] for i in range(1,5))
source = f'''// SPDX-License-Identifier: BSD-3-Clause
/dts-v1/;
/plugin/;
/ {{
    fragment@0 {{
        target-path = "/soc@0/pinctrl@f100000";
        __overlay__ {{
            mic_reset71: tb378fc-wcd-reset71-state {{
                pins = "gpio101";
                function = "gpio";
                drive-strength = <16>;
                bias-disable;
            }};
        }};
    }};
    fragment@1 {{
        target-path = "/soc@0/soundwire@6ad0000";
        __overlay__ {{
            status = "okay";
            #address-cells = <2>;
            #size-cells = <0>;
            mic_rx71: codec@0,4 {{
                compatible = "sdw20217010e00";
                reg = <0 4>;
                qcom,rx-port-mapping = <1 2 3 4 5 9>;
            }};
        }};
    }};
    fragment@2 {{
        target-path = "/soc@0/soundwire@7630000";
        __overlay__ {{
            status = "okay";
            #address-cells = <2>;
            #size-cells = <0>;
            mic_tx71: codec@0,3 {{
                compatible = "sdw20217010e00";
                reg = <0 3>;
                qcom,tx-port-mapping = <2 2 3 4>;
            }};
        }};
    }};
    fragment@3 {{
        target-path = "/";
        __overlay__ {{
            mic_codec71: tb378fc-wcd939x {{
                compatible = "qcom,wcd9390-codec";
                #sound-dai-cells = <1>;
                pinctrl-names = "default";
                pinctrl-0 = <&mic_reset71>;
                reset-gpios = <{tlmm} 101 1>;
                vdd-rxtx-supply = <{rail_id}>;
                vdd-io-supply = <{rail_id}>;
                vdd-buck-supply = <{rail_id}>;
                vdd-px-supply = <{rail_id}>;
                vdd-mic-bias-supply = <{bob_id}>;
                qcom,micbias1-microvolt = <1800000>;
                qcom,micbias2-microvolt = <1800000>;
                qcom,micbias3-microvolt = <1800000>;
                qcom,micbias4-microvolt = <1800000>;
                qcom,rx-device = <&mic_rx71>;
                qcom,tx-device = <&mic_tx71>;
            }};
        }};
    }};
}};
'''
dtso=work/'tb378fc-microphone-foundation71.dtso';dtso.write_text(source)
dtbo=work/'tb378fc-microphone-foundation71.dtbo'
subprocess.run(['dtc','-@','-I','dts','-O','dtb','-o',str(dtbo),str(dtso)],check=True)
merged=work/'offline-merged.dtb'
subprocess.run(['fdtoverlay','-i',str(base),'-o',str(merged),str(dtbo)],check=True)
after=parse(merged.read_bytes())
delta=[(path,name) for path in after for name,value in after[path].items() if before.get(path,{}).get(name)!=value]
assert all(path.startswith(('/tb378fc-wcd939x','/soc@0/pinctrl@f100000/tb378fc-wcd-reset71-state',
                           '/soc@0/soundwire@6ad0000','/soc@0/soundwire@7630000','/__symbols__')) for path,name in delta),delta
assert all(after.get(path,{}).get(name)==value for path,props in before.items() for name,value in props.items()
           if (path,name) not in delta)
record={'status':'CODEC_FOUNDATION_OFFLINE_NOT_LOADED_NO_CAPTURE_ROUTE',
        'base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),
        'overlay_sha256':hashlib.sha256(dtbo.read_bytes()).hexdigest(),
        'native_input_sha256':hashlib.sha256((root/'out/native-microphone69.json').read_bytes()).hexdigest(),
        'native_supplies':{'all_io_buck_rxtx_px':rail,'micbias':bob,'micbias_voltage':1800000},
        'px_voltage_differs_from_reference':True,
        'changed_properties':delta,'speaker_card_changed':False,
        'remaining':['Module import check against live exports','Live codec/SoundWire enumeration','Capture DAI/topology/UCM; no recording']}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
