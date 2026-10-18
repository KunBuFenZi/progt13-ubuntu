#!/usr/bin/env python3
"""Analyze an existing PCM recording against its song; never play or record audio."""
import argparse
import hashlib
import json
from pathlib import Path
import wave

import numpy as np


def read_pcm(path):
    with wave.open(str(path), 'rb') as stream:
        assert stream.getsampwidth() == 2 and stream.getcomptype() == 'NONE'
        rate, channels = stream.getframerate(), stream.getnchannels()
        data = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2')
    return data.reshape(-1, channels).astype(np.float64) / 32768, rate


def dbfs(values):
    return float(20 * np.log10(max(float(np.sqrt(np.mean(values ** 2))), 1e-12)))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('recording', type=Path)
parser.add_argument('stimulus', type=Path)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
recording, rate = read_pcm(args.recording)
stimulus, stimulus_rate = read_pcm(args.stimulus)
assert rate == stimulus_rate and rate % 8000 == 0
reference = stimulus.mean(axis=1)[::rate // 8000]
reference -= reference.mean()
length = len(reference)
channels = []
for index in range(recording.shape[1]):
    original = recording[:, index]
    signal = original[::rate // 8000]
    assert len(signal) >= length
    fft_size = 1 << (len(signal) + length - 2).bit_length()
    dots = np.fft.irfft(np.fft.rfft(signal, fft_size) *
                        np.fft.rfft(reference[::-1], fft_size), fft_size)
    dots = dots[length - 1:len(signal)]
    total = np.concatenate(([0.], np.cumsum(signal)))
    squares = np.concatenate(([0.], np.cumsum(signal ** 2)))
    energy = squares[length:] - squares[:-length] - (total[length:] - total[:-length]) ** 2 / length
    correlation = dots / np.sqrt(np.maximum(energy * np.sum(reference ** 2), 1e-24))
    best = int(np.argmax(np.abs(correlation)))
    per_second = [dbfs(original[start:start + rate])
                  for start in range(0, len(original) - rate + 1, rate)]
    channels.append({'channel': index, 'correlation_with_supplied_song': float(correlation[best]),
                     'lag_seconds': best / 8000, 'per_second_rms_dbfs': per_second,
                     'peak_dbfs': float(20 * np.log10(max(float(np.max(np.abs(original))), 1e-12))),
                     'clipped_samples': int(np.count_nonzero(np.abs(original) >= 32767 / 32768))})
result = {'recording_sha256': hashlib.sha256(args.recording.read_bytes()).hexdigest(),
          'stimulus_sha256': hashlib.sha256(args.stimulus.read_bytes()).hexdigest(),
          'rate': rate, 'seconds': len(recording) / rate,
          'method': '8kHz decimated, mean-centered sliding normalized waveform correlation; polarity may invert',
          'scope': 'Acoustic path evidence only; second microphone, speech quality and long-term operation require separate validation',
          'channels': channels}
args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
