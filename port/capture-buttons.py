#!/usr/bin/env python3
"""Observe volume press/release events without grabbing the input devices."""
import argparse
import json
from pathlib import Path
import select
import struct
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--seconds',type=int,default=180)
args=p.parse_args()
devices={}
for path in Path('/sys/class/input').glob('event*'):
    name=(path/'device/name').read_text().strip()
    if name in ('gpio-keys','pmic_resin'):
        stream=open('/dev/input/'+path.name,'rb',buffering=0)
        devices[stream]=(path.name,name)
print(json.dumps({'devices':list(devices.values()),'seconds':args.seconds}),flush=True)
assert len(devices)==2
record=struct.Struct('llHHi')
assert record.size==24
end=time.monotonic()+args.seconds
try:
    while time.monotonic()<end:
        ready,_,_=select.select(list(devices),[],[],max(0,min(1,end-time.monotonic())))
        for stream in ready:
            data=stream.read(record.size)
            sec,usec,kind,code,value=record.unpack(data)
            if kind==1 and code in (114,115):
                print(json.dumps({'device':devices[stream][0],'key':'volume_down' if code==114 else 'volume_up',
                                  'value':value,'event_seconds':sec+usec/1e6}),flush=True)
finally:
    for stream in devices:stream.close()
print('BUTTON_CAPTURE_FINISHED',flush=True)
