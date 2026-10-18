#!/usr/bin/env python3
"""Hash every real Iris-decoded frame without displaying or opening any camera."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--clip',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--frames',type=int,required=True)
args=parser.parse_args()
assert args.clip.is_relative_to('/run') and args.output.is_relative_to('/run')
assert not args.output.exists()
Gst.init(None)
started=time.monotonic()
pipeline=Gst.parse_launch('filesrc name=source ! h264parse ! video/x-h264,stream-format=byte-stream,alignment=au ! v4l2h264dec name=decoder capture-io-mode=mmap ! video/x-raw,format=NV12 ! videoconvert ! video/x-raw,format=I420 ! appsink name=sink emit-signals=true sync=false max-buffers=4 drop=false')
pipeline.get_by_name('source').set_property('location',str(args.clip))
proof={'status':'STARTED','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
       'decoder':pipeline.get_by_name('decoder').get_property('device'),
       'source_sha256':hashlib.sha256(args.clip.read_bytes()).hexdigest(),'frames':[]}
def frame(sink):
    sample=sink.emit('pull-sample');buf=sample.get_buffer()
    content=buf.extract_dup(0,buf.get_size())
    proof['frames'].append({'md5':hashlib.md5(content).hexdigest(),'bytes':len(content),'pts':buf.pts})
    proof['caps']=sample.get_caps().to_string()
    return Gst.FlowReturn.OK
pipeline.get_by_name('sink').connect('new-sample',frame)
bus=pipeline.get_bus()
try:
    assert pipeline.set_state(Gst.State.PLAYING)!=Gst.StateChangeReturn.FAILURE
    result=bus.timed_pop_filtered(25*Gst.SECOND,Gst.MessageType.EOS|Gst.MessageType.ERROR)
    assert result is not None,'Decode timed out'
    if result.type==Gst.MessageType.ERROR:
        err,debug=result.parse_error();raise RuntimeError(str(err)+' '+str(debug))
    assert len(proof['frames'])==args.frames,(len(proof['frames']),args.frames)
    assert proof['decoder']=='/dev/video0'
    proof['status']='REAL_IRIS_H264_DECODE_EOS_FRAME_HASHES'
except BaseException as e:
    proof.update(status='FAILED',error=str(e));raise
finally:
    pipeline.set_state(Gst.State.NULL)
    proof['wall_seconds']=time.monotonic()-started
    usage=resource.getrusage(resource.RUSAGE_SELF)
    proof['cpu_seconds']=usage.ru_utime+usage.ru_stime
    args.output.write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:v for k,v in proof.items() if k!='frames'}),flush=True)
