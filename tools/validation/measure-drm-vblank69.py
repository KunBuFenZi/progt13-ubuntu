#!/usr/bin/env python3
"""Read actual DRM CRTC vblank counters/timestamps without modesetting."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import struct
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--frames',type=int,default=120)
args=p.parse_args()
assert args.output.is_relative_to('/run') and not args.output.exists()
fd=os.open('/dev/dri/card0',os.O_RDWR|os.O_CLOEXEC)
request=0xC018643A
def wait(count):
    buf=bytearray(struct.pack('@IIqq',1,count,0,0))
    assert len(buf)==24
    fcntl.ioctl(fd,request,buf,True)
    kind,seq,sec,usec=struct.unpack('@IIqq',buf)
    return {'sequence':seq,'timestamp_us':sec*1000000+usec}
try:
    start=wait(1);end=wait(args.frames)
    sequence=(end['sequence']-start['sequence'])&0xffffffff
    delta=end['timestamp_us']-start['timestamp_us']
    assert sequence>=args.frames and delta>0
    record={'status':'REAL_CRTC_VBLANK_MEASURED','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'start':start,'end':end,'frames':sequence,'duration_us':delta,
            'measured_hz':sequence*1000000/delta,'kernel_drm_state':Path('/sys/kernel/debug/dri/0/state').read_text(),
            'monotonic':time.monotonic()}
    args.output.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k!='kernel_drm_state'}))
finally:
    os.close(fd)
