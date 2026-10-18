#!/usr/bin/env python3
"""Checked static-DT camera discovery. Does not open camera or microphone streams."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

directory = Path('/usr/share/tb378fc/camera74')
manifest = json.loads((directory / 'manifest.json').read_text())
assert b'lenovo,tb378fc-pmic-glink\0' in Path('/proc/device-tree/pmic-glink/compatible').read_bytes()
assert Path('/proc/device-tree/soc@0/cci@ac7b000/i2c-bus@0/camera@36').is_dir()
assert Path('/proc/device-tree/soc@0/cci@ac7c000/i2c-bus@0/camera@31').is_dir()
assert not int(Path('/proc/sys/kernel/tainted').read_text()) & 128
release = subprocess.check_output(['uname', '-r'], text=True).strip()
assert release == '7.2.0-tb378fc-wifi+'
exports = {s.split()[2].removeprefix('__ksymtab_') for s in Path('/proc/kallsyms').read_text().splitlines()
           if s.split()[2].startswith('__ksymtab_')}
loaded = {s.split()[0] for s in Path('/proc/modules').read_text().splitlines()}
pending = {}
for name, item in manifest['modules'].items():
    p = directory / name
    assert p.resolve().is_relative_to(directory.resolve())
    assert hashlib.sha256(p.read_bytes()).hexdigest() == item['sha256'], name
    assert item['vermagic'] == release + ' SMP preempt mod_unload aarch64'
    if p.stem.replace('-', '_') not in loaded:
        pending[name] = item
order = []; available = set(exports)
while pending:
    ready = sorted(name for name, item in pending.items() if not set(item['imports']) - available)
    assert ready, {name: sorted(set(item['imports']) - available) for name, item in pending.items()}
    for name in ready:
        available.update(pending.pop(name)['exports']); order.append(name)
record = {'time': time.time(), 'build_id': Path('/etc/tb378fc-build-id').read_text().strip(),
          'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'status': 'IMPORTS_AND_HASHES_VERIFIED', 'order': order, 'loaded_now': [],
          'camera_stream_opened': False, 'microphone_stream_opened': False}
out = Path('/run/evidence/camera74.json')
out.parent.mkdir(exist_ok=True)

def save(): out.write_text(json.dumps(record, indent=2) + '\n')

save()
# Register clock providers before CCI and sensors; the rest use the proven
# symbol dependency order. Do not unload any existing driver or restart DSPs.
clocks = ['clocks/camcc-sm8750.ko', 'clocks/cambistmclkcc-sm8750.ko']
order = [name for name in clocks if name in order] + [name for name in order if name not in clocks]
for name in order:
    result = subprocess.run(['insmod', str(directory / name)], capture_output=True, text=True, timeout=25)
    record['loaded_now'].append({'module': name, 'exit': result.returncode, 'stderr': result.stderr})
    save()
    result.check_returncode()
    assert not int(Path('/proc/sys/kernel/tainted').read_text()) & 128

def sensors():
    values = []
    for device in Path('/sys/bus/i2c/devices').iterdir():
        p = device / 'name'
        if p.exists() and p.read_text().strip() in ['gc08a8', 'ov13b10', 'tb378fc-ov13b10']:
            values.append({'device': device.name, 'name': p.read_text().strip(),
                           'driver': (device / 'driver').resolve().name if (device / 'driver').exists() else None,
                           'runtime_status': (device / 'power/runtime_status').read_text().strip()})
    return values

for attempt in range(40):
    record['sensors'] = sensors()
    if len(record['sensors']) == 2 and all(x['driver'] for x in record['sensors']): break
    time.sleep(.5)
record['video_devices'] = {p.name: (p / 'name').read_text().strip() for p in Path('/sys/class/video4linux').iterdir()}
record['media_devices'] = [p.name for p in Path('/dev').glob('media[0-9]*')]
record['taint'] = int(Path('/proc/sys/kernel/tainted').read_text())
record['status'] = 'TWO_SENSOR_DRIVERS_BOUND_NO_STREAM' if len(record['sensors']) == 2 and all(x['driver'] for x in record['sensors']) else 'SENSOR_PROBE_INCOMPLETE_NO_STREAM'
save()
print(json.dumps(record, indent=2))
assert record['status'] == 'TWO_SENSOR_DRIVERS_BOUND_NO_STREAM', record['status']
