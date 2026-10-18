#!/usr/bin/env python3
"""Prepare native ADSP inputs; does not enable or boot them in the desktop image."""
import hashlib
import io
import json
from pathlib import Path
import struct
import tarfile

ROOT=Path(__file__).resolve().parent.parent
nodes=json.loads((ROOT/'diagnostics/live-device-tree.json').read_text(encoding='utf-8'))['nodes']
by_path={n['path']:n['props'] for n in nodes}
by_id={n['props']['phandle']['cells'][0]:n for n in nodes if 'phandle' in n['props']}
native=by_path['/soc/remoteproc-adsp@03000000']
assert native['reg']['cells']==[0x3000000,0x10000]
assert native['firmware-name']['strings']==['adsp.mdt','adsp_dtb.mdt']
regions=[by_id[n]['props']['reg']['cells'] for n in native['memory-region']['cells']]
assert regions==[[0,0x9ee00000,0,0x3a80000],[0,0x9ed80000,0,0x80000]]
channel=by_path['/soc/remoteproc-adsp@03000000/glink-edge/qcom,pmic_glink_rpmsg']
assert channel['qcom,glink-channels']['strings']==['PMIC_RTR_ADSP_APPS']
directory=ROOT/'diagnostics/firmware/adsp'
manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
for name,record in manifest['files'].items():
    data=(directory/name).read_bytes()
    assert hashlib.sha256(data).hexdigest()==record['sha256'] and len(data)==record['size']
spans={}
for name,region in zip(('adsp.mdt','adsp_dtb.mdt'),regions):
    data=(directory/name).read_bytes()
    assert data[:6]==b'\x7fELF\x01\x01'
    offset=struct.unpack_from('<I',data,28)[0]
    stride,count=struct.unpack_from('<HH',data,42)
    loads=[]
    for index in range(count):
        kind,off,va,pa,filesz,memsz,flags,align=struct.unpack_from('<8I',data,offset+index*stride)
        if kind!=1 or not memsz or (flags>>24)&7==2:continue
        assert flags & (1<<27),'Firmware relocation must be supported for the native reservation'
        if filesz:
            segment=directory/(name[:-4]+f'.b{index:02d}')
            assert segment.exists() and segment.stat().st_size==filesz,(name,index,filesz)
        loads.append((pa,pa+memsz))
    span=(max(end for start,end in loads)+4095)//4096*4096-min(start for start,end in loads)
    assert span<=region[3],(name,span,region)
    spans[name]={'load_segments':len(loads),'span':span,'native_region':region}
out=ROOT/'out/adsp-native'
out.mkdir(exist_ok=True)
with tarfile.open(out/'adsp-firmware.tar','w') as tar:
    for name in sorted(manifest['files']):
        data=(directory/name).read_bytes()
        item=tarfile.TarInfo('usr/lib/firmware/qcom/sm8750/tb378fc/'+name)
        item.mode=0o644;item.size=len(data);tar.addfile(item,io.BytesIO(data))
dts='''// SPDX-License-Identifier: BSD-3-Clause
/* Native ADSP preparation; separate candidate, not part of the tested desktop. */
#include "sm8750-lenovo-tb378fc-keys.dts"

&adspslpi_mem {
    reg = <0x0 0x9ee00000 0x0 0x3a80000>;
};
&q6_adsp_dtb_mem {
    reg = <0x0 0x9ed80000 0x0 0x80000>;
};
&remoteproc_adsp {
    /* Register base is verified on this board's running native driver. */
    reg = <0x0 0x03000000 0x0 0x10000>;
    firmware-name = "qcom/sm8750/tb378fc/adsp.mdt",
                    "qcom/sm8750/tb378fc/adsp_dtb.mdt";
    status = "okay";
};
'''
(ROOT/'port/sm8750-lenovo-tb378fc-adsp.dts').write_text(dts,encoding='utf-8')
proof={'status':'NATIVE_ADSP_INPUTS_PREPARED_NOT_COMPILED_OR_BOOTED',
       'spans':spans,'files':manifest['files'],
       'tar_sha256':hashlib.sha256((out/'adsp-firmware.tar').read_bytes()).hexdigest(),
       'remaining':'Enable PAS and dependencies in a separate kernel, validate GLINK before battery/audio consumers.'}
(out/'manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'status':proof['status'],'spans':spans},indent=2))
