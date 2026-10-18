#!/usr/bin/env python3
"""User-authorized bounded microphone recording with the supplied song stimulus."""
import array
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time
import wave

out = Path(os.environ.get('TB378FC_MIC75_OUT', '/run/evidence/microphone75'))
assert out.is_relative_to('/run/evidence')
out.mkdir(parents=True, exist_ok=True)
pcm = Path('/proc/asound/card0/pcm2c/sub0/status')
assert pcm.read_text().strip() == 'closed'
assert not int(Path('/proc/sys/kernel/tainted').read_text()) & 128
assert Path('/etc/tb378fc-build-id').read_text().strip() in {
    '72f0dd4b147b8040926ae1a46990dd8de8c09672050b39ba121bb55d1136cba8',
    '98516c6d7168e5f9aa6007107bd981687bf321f7faf4b501526d95a39f80ad86',
    '4644f0193d0f602e1d3fb067afcc11cdff36a2d96454d433245f09643960400d',
}
record = {'status': 'STARTING', 'user_authorized_recording': True,
          'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'stimulus': 'User supplied 浮夸, six second excerpt attenuated by 18.06 dB',
          'stimulus_gain': 0.125,
          'steps': []}
# aplay bypasses the desktop volume. Attenuate the actual PCM, so later raw
# hardware tests also respect the user's request for quieter test music.
quiet_stimulus = out / 'stimulus-quiet.wav'
with wave.open('/run/fukua-test-original.wav', 'rb') as source:
    assert source.getsampwidth() == 2 and source.getcomptype() == 'NONE'
    params = source.getparams()
    assert params.framerate == 48000 and params.nchannels == 2 and params.nframes <= 6 * 48000
    quieter = array.array('h', source.readframes(params.nframes))
    for index, value in enumerate(quieter):
        quieter[index] = round(value * record['stimulus_gain'])
with wave.open(str(quiet_stimulus), 'wb') as target:
    target.setparams(params)
    target.writeframes(quieter.tobytes())


def run(argv, timeout=15):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    record['steps'].append({'argv': argv, 'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    return result


before = run(['amixer', '-c', '0', 'contents']).stdout
(out / 'mixer-before.txt').write_text(before)
state = out / 'mixer-before.state'
run(['alsactl', '-f', str(state), 'store', '0']).check_returncode()
capture = None
inspect = Path('/sys/kernel/debug/tb378fc-apm75/state')


def snapshot(label):
    if inspect.exists():
        (out / ('apm-' + label + '.txt')).write_text(inspect.read_text())
    if label == '100ms':
        for key, path in {
            'swr-master': '/sys/kernel/debug/soundwire/master-3-0/qualcomm-sdw/qualcomm-registers',
            'swr-slave': '/sys/kernel/debug/soundwire/master-3-0/sdw:3:0:0217:010e:00:3/registers',
            'tx-macro': '/sys/kernel/debug/regmap/6ae0000.codec-tx_macro/registers',
        }.items():
            source = Path(path)
            if source.exists():
                (out / (key + '-active.txt')).write_text(source.read_text())


try:
    tuning = Path('/usr/share/tb378fc/microphone73/Mic73.conf').read_text()
    enable = tuning.split('EnableSequence [', 1)[1].split(']', 1)[0]
    if os.environ.get('TB378FC_MIC75_PACK_DEC01', '1') == '1':
        # Current Audioreach codec-DMA config selects mask 0b11. Keep the
        # native ADC and SoundWire input wiring, pack it into DEC0/DEC1.
        for old, new in [('TX_DEC2', 'TX_DEC0'), ('TX_DEC5', 'TX_DEC1'),
                         ('TX DEC2', 'TX DEC0'), ('TX DEC5', 'TX DEC1'),
                         ('TX SMIC MUX2', 'TX SMIC MUX0'), ('TX SMIC MUX5', 'TX SMIC MUX1'),
                         ('Mixer DEC2', 'Mixer DEC0'), ('Mixer DEC5', 'Mixer DEC1')]:
            enable = enable.replace(old, new)
        record['route_variant'] = 'native_ADC1_ADC3_SWR4_SWR8_packed_DEC0_DEC1_for_DMA_mask3'
    adc_mode = os.environ.get('TB378FC_MIC75_ADC_MODE', 'ADC_LP')
    assert adc_mode in ['ADC_LP', 'ADC_HIFI']
    if adc_mode != 'ADC_LP':
        enable = enable.replace(' ADC_LP', ' ' + adc_mode)
    record['adc_mode'] = adc_mode
    for value in re.findall(r'cset "([^"]+)"', enable):
        run(['amixer', '-c', '0', 'cset', *shlex.split(value)]).check_returncode()
    (out / 'mixer-enabled.txt').write_text(run(['amixer', '-c', '0', 'contents']).stdout)
    with (out / 'arecord.txt').open('w') as log:
        capture = subprocess.Popen(['strace', '-o', str(out / 'arecord.strace'), '-e', 'trace=ioctl,poll,ppoll', 'arecord', '--nonblock', '--buffer-time=1000000', '--period-time=250000', '-D', 'hw:0,2', '-f', 'S16_LE', '-r', '48000',
                                    '-c', '2', '-t', 'wav', '-d', '10', str(out / 'microphone-song.wav')], stdout=log, stderr=log, start_new_session=True)
        time.sleep(.1)
        snapshots = {}
        for name in ['MultiMedia3 Mixer', 'device120.logger1', 'TX_CODEC_DMA_TX_3 Capture',
                     'TX AIF1_CAP', 'TX_AIF1 Capture', 'TX SWR_INPUT4', 'TX SWR_INPUT8',
                     'ADC1', 'ADC3', 'ADC1_OUTPUT', 'ADC3_OUTPUT', 'WCD AIF1 Capture',
                     'MIC BIAS1', 'MIC BIAS3']:
            for path in Path('/sys/kernel/debug/asoc/Lenovo-TB378FC').rglob(name):
                if path.is_file(): snapshots[str(path)] = path.read_text()
        record['capture_state_at_100ms'] = pcm.read_text()
        snapshot('100ms')
        record['hw_params'] = Path('/proc/asound/card0/pcm2c/sub0/hw_params').read_text()
        (out / 'dapm-at-100ms.json').write_text(json.dumps(snapshots, indent=2))
        time.sleep(.9)
        record['capture_state_at_1s'] = pcm.read_text()
        snapshot('1s')
        if capture.poll() is not None:
            raise RuntimeError('Capture exited before stimulus; see arecord.txt')
        time.sleep(1)
        record['playback'] = run(['aplay', '-D', 'hw:0,0', str(quiet_stimulus)], timeout=10).returncode
        record['capture_state_after_playback'] = pcm.read_text()
        snapshot('after-playback')
        capture.wait(timeout=8)
        assert capture.returncode == 0
    with wave.open(str(out / 'microphone-song.wav'), 'rb') as wav:
        record['channels'], record['sample_width'], record['rate'], frames, *_ = wav.getparams()
        data = wav.readframes(frames)
    samples = array.array('h', data)
    record['frames'] = frames
    record['sha256'] = hashlib.sha256(data).hexdigest()
    windows = []
    for second in range(10):
        channels = []
        for channel in range(2):
            values = samples[(second * 48000 * 2 + channel):((second + 1) * 48000 * 2):2]
            mean = sum(values) / len(values)
            rms = math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))
            channels.append({'rms_dbfs': 20 * math.log10(max(rms, 1e-9) / 32768),
                             'peak': max(abs(x) for x in values), 'mean': mean,
                             'distinct_samples': len(set(values))})
        windows.append(channels)
    record.update(status='CAPTURED_NOT_YET_ACOUSTICALLY_ACCEPTED', seconds=windows)
except Exception as exc:
    record.update(status='TEST_FAILED', error=str(exc))
finally:
    if capture and capture.poll() is None:
        os.killpg(capture.pid, signal.SIGTERM)
        try: capture.wait(timeout=5)
        except subprocess.TimeoutExpired: os.killpg(capture.pid, signal.SIGKILL); capture.wait(timeout=3)
    run(['alsactl', '-f', str(state), 'restore', '0'])
    after = run(['amixer', '-c', '0', 'contents']).stdout
    (out / 'mixer-after.txt').write_text(after)
    record['mixer_identical'] = before == after
    record['pcm_after'] = pcm.read_text().strip()
    record['taint_after'] = int(Path('/proc/sys/kernel/tainted').read_text())
    record['arecord_log'] = (out / 'arecord.txt').read_text() if (out / 'arecord.txt').exists() else None
    (out / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: v for k, v in record.items() if k != 'steps'}, indent=2))
