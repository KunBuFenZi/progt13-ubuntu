#!/usr/bin/env python3
"""Bounded image-only libcamera test with real RGB frames and explicit cleanup."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--camera', choices=['front', 'rear'], required=True)
p.add_argument('--frames', type=int, default=75)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--width', type=int)
p.add_argument('--height', type=int)
p.add_argument('--minimum-seconds', type=float, default=0)
p.add_argument('--white-red', type=float)
p.add_argument('--white-blue', type=float)
args = p.parse_args()
assert 1 <= args.frames <= 900
assert 0 <= args.minimum_seconds <= 10
assert bool(args.width) == bool(args.height)
args.output.mkdir(parents=True, exist_ok=True)
Gst.init(None)
camera = '/base/soc@0/cci@ac7c000/i2c-bus@0/camera@31' if args.camera == 'front' else '/base/soc@0/cci@ac7b000/i2c-bus@0/camera@36'
w, h = (1280, 720) if args.camera == 'front' else (1052, 780)
if args.width:
    assert 16 <= args.width <= 4208 and 16 <= args.height <= 3120
    w, h = args.width, args.height
pipeline = Gst.parse_launch(f'libcamerasrc name=camera camera-name={camera} ! video/x-raw,width={w},height={h} ! videoconvert ! video/x-raw,format=RGB ! appsink name=sink max-buffers=2 drop=true sync=false')
if args.white_red is not None:
    assert args.white_blue is not None
    pipeline.get_by_name('camera').set_property('awb-enable', False)
    Gst.util_set_object_arg(pipeline.get_by_name('camera'), 'colour-gains', f'< (float){args.white_red}, (float){args.white_blue} >')
sink = pipeline.get_by_name('sink')
bus = pipeline.get_bus()
start = time.monotonic()
frames = []
record = {'camera': args.camera, 'status': 'STARTING', 'microphone_stream_opened': False,
          'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
try:
    assert pipeline.set_state(Gst.State.PLAYING) != Gst.StateChangeReturn.FAILURE
    while len(frames) < args.frames or time.monotonic() - start < args.minimum_seconds:
        sample = sink.emit('try-pull-sample', 2 * Gst.SECOND)
        message = bus.pop_filtered(Gst.MessageType.ERROR)
        if message:
            error, debug = message.parse_error()
            raise RuntimeError(str(error) + '\n' + str(debug))
        assert sample is not None, 'No image within two seconds'
        info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
        buffer = sample.get_buffer()
        data = buffer.extract_dup(0, buffer.get_size())
        frames.append({'pts': buffer.pts, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        assert time.monotonic() - start < 15, 'Image test exceeded time bound'
    width, height = info.width, info.height
    rgb = b''.join(data[info.offset[0] + y * info.stride[0]:info.offset[0] + y * info.stride[0] + width * 3] for y in range(height))
    (args.output / 'last.ppm').write_bytes(f'P6\n{width} {height}\n255\n'.encode() + rgb)
    assert len(set(rgb)) > 40, 'Image lacks signal variation'
    assert len({f['sha256'] for f in frames}) > len(frames) * .8, 'Frames do not change'
    record.update(status='RGB_FRAMES_CAPTURED', width=width, height=height,
                  elapsed=time.monotonic() - start, frames=frames)
finally:
    cleanup = pipeline.set_state(Gst.State.NULL)
    record.update(cleanup=str(cleanup), taint=int(Path('/proc/sys/kernel/tainted').read_text()))
    (args.output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
assert not record['taint'] & 128
print(json.dumps({k:v for k,v in record.items() if k != 'frames'}))
