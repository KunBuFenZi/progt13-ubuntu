#!/usr/bin/env python3
"""Inspect packed RAW10 camera evidence; render a basic, untuned Bayer preview."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('file', type=Path)
p.add_argument('--width', type=int, required=True)
p.add_argument('--height', type=int, required=True)
p.add_argument('--stride', type=int, required=True)
p.add_argument('--pattern', choices=['RGGB', 'GRBG'], required=True)
args = p.parse_args()
data = args.file.read_bytes()
size = args.stride * args.height
assert len(data) and len(data) % size == 0
frames = []
for n in range(len(data) // size):
    frame = data[n * size:(n + 1) * size]
    groups = np.frombuffer(frame, dtype=np.uint8).reshape(args.height, args.stride)[:, :args.width * 5 // 4].reshape(args.height, -1, 5).astype(np.uint16)
    raw = np.empty((args.height, args.width), dtype=np.uint16)
    for i in range(4):
        raw[:, i::4] = (groups[:, :, i] << 2) | ((groups[:, :, 4] >> (2 * i)) & 3)
    frames.append({'frame': n, 'sha256': hashlib.sha256(frame).hexdigest(),
                   'minimum': int(raw.min()), 'maximum': int(raw.max()),
                   'mean': float(raw.mean()), 'stddev': float(raw.std()),
                   'percentiles': np.percentile(raw, [1, 10, 50, 90, 99]).tolist()})
    if n != len(data) // size - 1:
        continue
    # Downsample Bayer quads without assuming a calibrated ISP. White balance
    # and tone mapping are for inspection only, never camera-quality evidence.
    channels = {args.pattern[y * 2 + x] + str(y * 2 + x): raw[y::2, x::2].astype(np.float32)
                for y in range(2) for x in range(2)}
    rgb = np.stack([np.mean([v for k, v in channels.items() if k[0] == c], axis=0)
                    for c in 'RGB'], axis=2)
    black = float(np.percentile(rgb, 1))
    rgb = np.maximum(rgb - black, 0)
    means = np.maximum(rgb.mean(axis=(0, 1)), 1)
    rgb *= means[1] / means
    high = max(float(np.percentile(rgb, 99.5)), 1)
    rgb = np.clip(rgb / high, 0, 1) ** (1 / 2.2)
    preview = Image.fromarray((rgb * 255).astype(np.uint8))
    preview.thumbnail((1000, 1000))
    preview.save(args.file.with_suffix('.preview.png'))
report = {'width': args.width, 'height': args.height, 'stride': args.stride,
          'pattern': args.pattern, 'frame_count': len(frames), 'frames': frames,
          'preview': 'Uncalibrated quad downsample, gray-world WB and auto stretch'}
args.file.with_suffix('.inspection.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
