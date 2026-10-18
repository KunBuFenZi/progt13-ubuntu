#!/usr/bin/env python3
"""Board-specific firmware and UCM files for the restricted playback driver."""
import hashlib
import json
from pathlib import Path


def add_audio_overlay(add, links, amp_firmware, topology):
    proof = json.loads(amp_firmware.with_name('manifest.json').read_text())
    data = amp_firmware.read_bytes()
    assert hashlib.sha256(data).hexdigest() == proof['output_sha256']
    add('usr/lib/firmware/awinic/tb378fc/aw88480-native-music.acf',data)
    data = topology.read_bytes()
    assert data[:4] == b'CoSA'
    add('usr/lib/firmware/qcom/sm8750/Lenovo-TB378FC-tplg.bin',data)
    directory = 'usr/share/alsa/ucm2/Qualcomm/sm8750/Lenovo-TB378FC/'
    # Hardware gain remains 48dB below native Music. PipeWire uses software
    # attenuation on top; this does not replace the missing vendor protection.
    for name in ('Lenovo-TB378FC.conf','HiFi.conf'):
        add(directory+name,(Path(__file__).resolve().parent/'audio'/name).read_bytes())
    links['usr/share/alsa/ucm2/conf.d/sm8750/Lenovo-TB378FC.conf'] = '../../Qualcomm/sm8750/Lenovo-TB378FC/Lenovo-TB378FC.conf'
