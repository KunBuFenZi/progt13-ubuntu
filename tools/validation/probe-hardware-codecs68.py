#!/usr/bin/env python3
"""Exercise a named Iris hardware decoder and hash its actual output frames."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import struct
import time
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--codec',choices=['hevc','vp9','av1'],required=True)
p.add_argument('--clip',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--frames',type=int,default=60)
args=p.parse_args()
assert args.clip.is_relative_to('/run') and args.output.is_relative_to('/run')
assert not args.output.exists()
Gst.init(None)
factory={'hevc':'v4l2h265dec','vp9':'v4l2vp9dec','av1':'v4l2av1dec'}[args.codec]
if args.codec=='hevc':
    source='filesrc name=source ! h265parse ! video/x-h265,stream-format=byte-stream,alignment=au'
else:
    raw=args.clip.read_bytes()
    signature,version,length,fourcc,width,height,rate,scale,count,unused=struct.unpack_from('<4sHH4sHHIIII',raw)
    assert signature==b'DKIF' and version==0 and length==32
    assert fourcc=={'vp9':b'VP90','av1':b'AV01'}[args.codec]
    assert rate and scale
    packets=[]
    offset=length
    while offset<len(raw):
        size,pts=struct.unpack_from('<IQ',raw,offset);offset+=12
        assert size and offset+size<=len(raw)
        packets.append((raw[offset:offset+size],pts*scale*Gst.SECOND//rate))
        offset+=size
    assert len(packets)==args.frames
    caps='video/x-vp9' if args.codec=='vp9' else 'video/x-av1,stream-format=obu-stream,alignment=tu'
    source=f'appsrc name=source format=time caps="{caps},width={width},height={height},framerate={rate}/{scale}" ! '+('vp9parse' if args.codec=='vp9' else 'av1parse ! video/x-av1,stream-format=obu-stream,alignment=tu')
pipeline=Gst.parse_launch(source+f' ! {factory} name=decoder capture-io-mode=mmap ! video/x-raw,format=NV12 ! videoconvert ! video/x-raw,format=I420 ! appsink name=sink emit-signals=true sync=false max-buffers=4 drop=false')
if args.codec=='hevc':
    pipeline.get_by_name('source').set_property('location',str(args.clip))
else:
    iterator=iter(packets)
    def feed(source,size_hint):
        packet=next(iterator,None)
        if packet is None:
            source.emit('end-of-stream');return
        data,pts=packet
        buf=Gst.Buffer.new_allocate(None,len(data),None);buf.fill(0,data)
        buf.pts=pts;buf.dts=pts;buf.duration=scale*Gst.SECOND//rate
        result=source.emit('push-buffer',buf)
        assert result in (Gst.FlowReturn.OK,Gst.FlowReturn.FLUSHING),str(result)
    pipeline.get_by_name('source').connect('need-data',feed)
proof={'status':'STARTED','codec':args.codec,'factory':factory,
       'decoder':pipeline.get_by_name('decoder').get_property('device'),
       'uid':__import__('os').getuid(),
       'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
       'source_sha256':hashlib.sha256(args.clip.read_bytes()).hexdigest(),'frames':[]}
def frame(sink):
    sample=sink.emit('pull-sample');buf=sample.get_buffer();data=buf.extract_dup(0,buf.get_size())
    proof['frames'].append({'md5':hashlib.md5(data).hexdigest(),'bytes':len(data),'pts':buf.pts})
    proof['caps']=sample.get_caps().to_string()
    return Gst.FlowReturn.OK
pipeline.get_by_name('sink').connect('new-sample',frame)
start=time.monotonic()
try:
    assert proof['decoder']=='/dev/video0'
    assert pipeline.set_state(Gst.State.PLAYING)!=Gst.StateChangeReturn.FAILURE
    result=pipeline.get_bus().timed_pop_filtered(25*Gst.SECOND,Gst.MessageType.ERROR|Gst.MessageType.EOS)
    assert result is not None,'Hardware decode timed out'
    if result.type==Gst.MessageType.ERROR:
        err,debug=result.parse_error();raise RuntimeError(str(err)+' '+str(debug))
    assert len(proof['frames'])==args.frames,(len(proof['frames']),args.frames)
    proof['status']='IRIS_HARDWARE_DECODE_EOS_HASHES_PENDING_REFERENCE_COMPARE'
except BaseException as error:
    proof.update(status='FAILED',error=str(error));raise
finally:
    pipeline.set_state(Gst.State.NULL)
    proof['wall_seconds']=time.monotonic()-start
    usage=resource.getrusage(resource.RUSAGE_SELF);proof['cpu_seconds']=usage.ru_utime+usage.ru_stime
    args.output.write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:v for k,v in proof.items() if k!='frames'}),flush=True)
