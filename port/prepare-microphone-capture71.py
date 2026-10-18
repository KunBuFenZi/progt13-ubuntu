#!/usr/bin/env python3
"""Prepare additive capture links and topology; this does not open a microphone."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live-controller-alias',action='store_true')
args=parser.parse_args()
work=root/('out/microphone-capture71b' if args.live_controller_alias else 'out/microphone-capture71')
work.mkdir(exist_ok=False)
base=root/'out/microphone-foundation71/offline-merged.dtb'
data=base.read_bytes()
_,_,pos,strings=struct.unpack_from('>4I',data)
nodes,stack={},[]
while True:
    token,=struct.unpack_from('>I',data,pos);pos+=4
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
cell=lambda data: struct.unpack('>I',data)[0]
def compatible(name):
    found=[(path,props) for path,props in nodes.items() if name.encode() in props.get('compatible',b'').split(b'\0')]
    assert len(found)==1,(name,found)
    path,props=found[0]
    return path,cell(props['phandle'])
apm,apm_id=compatible('qcom,q6apm')
bedais,bedais_id=compatible('qcom,q6apm-lpass-dais')
txmacro='/soc@0/codec@6ae0000'
tx_id=cell(nodes[txmacro]['phandle'])
routes=nodes['/sound']['audio-routing'].rstrip(b'\0').decode().split('\0')
assert routes==['Speakers','Amp0 OUT','Speakers','Amp1 OUT','Speakers','Amp2 OUT','Speakers','Amp3 OUT']
routes+=['AMIC1','MIC BIAS1','AMIC4','MIC BIAS3',
         'TX SWR_INPUT4','ADC1_OUTPUT','TX SWR_INPUT8','ADC3_OUTPUT']
route_text=', '.join(json.dumps(value) for value in routes)
bus_fragment='''fragment@0 {
        target-path = "/soc@0/soundwire@7630000";
        capture_swr71: __overlay__ { #sound-dai-cells = <1>; };
    };'''
if args.live_controller_alias:
    bus_props=nodes['/soc@0/soundwire@7630000']
    properties='\n'.join(name+' = ['+value.hex(' ')+'];' for name,value in bus_props.items()
                         if name not in ['phandle','linux,phandle','status'])
    bus_fragment=f'''fragment@0 {{
        target-path = "/soc@0/soundwire@7630000";
        __overlay__ {{ status = "disabled"; }};
    }};
    fragment@2 {{
        target-path = "/soc@0";
        __overlay__ {{
            capture_swr71: tb378fc-soundwire-tx@7630000 {{
                {properties}
                status = "okay";
                capture_tx71: codec@0,3 {{
                    compatible = "sdw20217010e00";
                    reg = <0 3>;
                    qcom,tx-port-mapping = <2 2 3 4>;
                }};
            }};
        }};
    }};
    fragment@3 {{
        target-path = "/tb378fc-wcd939x";
        __overlay__ {{ qcom,tx-device = <&capture_tx71>; }};
    }};'''
source=f'''// SPDX-License-Identifier: BSD-3-Clause
/dts-v1/;
/plugin/;
/ {{
    {bus_fragment}
    fragment@1 {{
        target-path = "/sound";
        __overlay__ {{
            audio-routing = {route_text};
            wcd-capture-dai-link {{
                link-name = "WCD Capture";
                convert-rate = <48000>;
                convert-channels = <2>;
                convert-sample-format = "s16_le";
                cpu {{ sound-dai = <{bedais_id} 120>; }};
                codec {{ sound-dai = <&mic_codec71 1>, <&capture_swr71 0>, <{tx_id} 0>; }};
                platform {{ sound-dai = <{apm_id}>; }};
            }};
        }};
    }};
}};
'''
dtso=work/'tb378fc-microphone-capture71.dtso';dtso.write_text(source)
dtbo=work/'tb378fc-microphone-capture71.dtbo'
subprocess.run(['dtc','-@','-I','dts','-O','dtb','-o',str(dtbo),str(dtso)],check=True)
merged=work/'offline-merged.dtb'
subprocess.run(['fdtoverlay','-i',str(base),'-o',str(merged),str(dtbo)],check=True)
base_m4=(root/'port/Lenovo-TB378FC.m4').read_text()
extra='''
# Native WCD939x analog microphones through TX DMA3. No stream is opened here.
include(`audioreach/device-subgraph.m4')
STREAM_SG_PCM_ADD(audioreach/subgraph-stream-capture.m4, FRONTEND_DAI_MULTIMEDIA3,
    `S16_LE', 48000, 48000, 1, 2,
    0x00004003, 0x00004003, 0x00006200, `110000')
DEVICE_SG_ADD(audioreach/subgraph-device-codec-dma-capture.m4, `TX_CODEC_DMA_TX_3', TX_CODEC_DMA_TX_3,
    `S16_LE', 48000, 48000, 2, 2,
    LPAIF_INTF_TYPE_RXTX, CODEC_INTF_IDX_TX3, 0, DATA_FORMAT_FIXED_POINT,
    0x00004020, 0x00004020, 0x00006300)
STREAM_DEVICE_CAPTURE_MIXER(FRONTEND_DAI_MULTIMEDIA3, ``TX_CODEC_DMA_TX_3'')
STREAM_DEVICE_CAPTURE_ROUTE(FRONTEND_DAI_MULTIMEDIA3, ``MultiMedia3 Mixer'', ``TX_CODEC_DMA_TX_3, device120.logger1'')
'''
m4=work/'Lenovo-TB378FC-microphone71.m4';m4.write_text(base_m4+extra)
config=work/'Lenovo-TB378FC.conf'
with config.open('w') as out:
    subprocess.run(['m4','-I',str(root/'reference/audioreach-topology'),str(m4)],stdout=out,check=True)
tplg=work/'Lenovo-TB378FC-tplg.bin'
subprocess.run(['alsatplg','-c',str(config),'-o',str(tplg)],check=True)
subprocess.run(['alsatplg','-d',str(tplg),'-o',str(work/'decoded.conf')],check=True)
assert 'MultiMedia3 Capture' in (work/'decoded.conf').read_text()
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
record={'status':'OFFLINE_CAPTURE_CANDIDATE_NO_RECORDING',
        'live_controller_alias':args.live_controller_alias,
        'live_alias_reason':'Kernel OF overlays ignore phandles on preexisting nodes; clone only the idle TX controller, with identical hardware properties',
        'files':{path.name:sha(path) for path in [dtso,dtbo,m4,config,tplg,merged]},
        'base_topology_sha256':sha(root/'out/topology-tb378fc/Lenovo-TB378FC-tplg.bin'),
        'speaker_m4_unchanged_prefix':True,'backend':{'dai':120,'apm_path':apm,'apm_phandle':apm_id,
                                                    'bedais_path':bedais,'bedais_phandle':bedais_id,'tx_phandle':tx_id},
        'native_routes':{'primary':'AMIC4/ADC3/port3-channel1/SWR_MIC8/DEC5',
                         'secondary':'AMIC1/ADC1/port2-channel1/SWR_MIC4/DEC2'},
        'remaining':['Apply capture overlay and rebind sound card only','Mixer/UCM validation without recording']}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
