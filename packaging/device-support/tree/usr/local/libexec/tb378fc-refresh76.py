#!/usr/bin/env python3
"""Load checked board DFPS support after120Hz desktop and discover existing media."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory', type=Path, default=Path('/usr/share/tb378fc/refresh76'))
args = parser.parse_args()
directory = args.directory
manifest = json.loads((directory / 'manifest.json').read_text())
module = directory / 'refresh-live76.ko'
assert hashlib.sha256(module.read_bytes()).hexdigest() == manifest['module_sha256']
assert subprocess.check_output(['uname', '-r'], text=True).strip() == '7.2.0-tb378fc-wifi+'
assert subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip() == '7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
assert b'lenovo,tb378fc-pmic-glink\0' in Path('/proc/device-tree/pmic-glink/compatible').read_bytes()
assert not int(Path('/proc/sys/kernel/tainted').read_text()) & 128
assert not any(Path('/sys/module/' + name).exists() for name in ['refresh_live75', 'refresh_modes_live69'])
exports = {s.split()[2].removeprefix('__ksymtab_') for s in Path('/proc/kallsyms').read_text().splitlines()
           if s.split()[2].startswith('__ksymtab_')}
assert not set(manifest['imports']) - exports
record = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'build_id': Path('/etc/tb378fc-build-id').read_text().strip(),
          'module_sha256': manifest['module_sha256'], 'module_loaded_now': False,
          'media_restarted': False, 'recorded_audio': False, 'camera_capture_started': False,
          'changed_refresh_mode': False, 'steps': []}
out = Path('/run/evidence/refresh76-startup.json')
out.parent.mkdir(exist_ok=True)


def save():
    out.write_text(json.dumps(record, indent=2) + '\n')


def run(args, timeout=8):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    record['steps'].append({'args': args, 'exit': result.returncode, 'stderr': result.stderr})
    save()
    result.check_returncode()
    return result.stdout


try:
    if not Path('/sys/module/refresh_live76').exists():
        # Cold GDM -> user-session handover can precede the first completed
        # display commit. ENODEV is a side-effect-free readiness refusal in
        # this pinned module: every gate is before callback installation.
        # Retry that refusal only, never an arbitrary module error or oops.
        for attempt in range(20):
            result = subprocess.run(['insmod', str(module), 'expose144=1'],
                                    capture_output=True, text=True, timeout=12)
            record['steps'].append({'module_load_attempt': attempt + 1,
                                    'exit': result.returncode, 'stderr': result.stderr,
                                    'monotonic': time.monotonic()})
            save()
            if result.returncode == 0:
                break
            if ('No such device' not in result.stderr or
                    Path('/sys/module/refresh_live76').exists() or
                    int(Path('/proc/sys/kernel/tainted').read_text()) & 128):
                result.check_returncode()
            if attempt == 19:
                result.check_returncode()
            time.sleep(1)
        record['module_loaded_now'] = True
    assert Path('/sys/module/refresh_live76/parameters/expose144').read_text().strip() == 'Y'
    Path('/sys/module/refresh_live76/parameters/armed').write_text('1')
    record['refresh_state'] = Path('/sys/kernel/debug/tb378fc-refresh76/state').read_text()
    save()
    user = ['runuser', '-u', 'pad', '--', 'env', 'XDG_RUNTIME_DIR=/run/user/1000',
            'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus']

    def media_state():
        objects = json.loads(run(user + ['pw-dump']))
        nodes = [o['info'] for o in objects if o.get('type') == 'PipeWire:Interface:Node' and 'info' in o]
        props = [node.get('props', {}) for node in nodes]
        cameras = sorted({p.get('api.libcamera.location') for p in props
                          if p.get('device.api') == 'libcamera' and p.get('media.class') == 'Video/Source'})
        input_ready = any(p.get('media.class') == 'Audio/Source' and
                          p.get('factory.name') == 'api.alsa.pcm.source' for p in props)
        output_ready = any(p.get('media.class') == 'Audio/Sink' and
                           p.get('factory.name') == 'api.alsa.pcm.sink' for p in props)
        busy = any(n.get('state') == 'running' and n.get('props', {}).get('media.class', '').startswith('Stream/')
                   for n in nodes)
        return {'cameras': cameras, 'alsa_input': input_ready, 'alsa_output': output_ready,
                'streams_running': busy, 'ready': cameras == ['back', 'front'] and input_ready and output_ready}

    state = media_state()
    # Native libcamera devices may arrive after the media monitor's first
    # enumeration. Allow normal discovery, then refresh that monitor once.
    for attempt in range(10):
        if state['ready']:
            break
        time.sleep(.5)
        state = media_state()
    if not state['ready']:
        for attempt in range(15):
            if not state['streams_running']:
                break
            time.sleep(1)
            state = media_state()
        if not state['streams_running']:
            run(user + ['systemctl', '--user', 'try-restart', 'wireplumber.service'], timeout=12)
            record['media_restarted'] = True
            for attempt in range(10):
                time.sleep(.5)
                state = media_state()
                if state['ready']:
                    break
    record['media'] = state
    record['status'] = 'REFRESH_AND_MEDIA_READY' if state['ready'] else 'REFRESH_READY_MEDIA_ENUMERATION_INCOMPLETE'
    record['taint'] = int(Path('/proc/sys/kernel/tainted').read_text())
    assert not record['taint'] & 128
except Exception as exc:
    record.update(status='FAILED', error=str(exc))
    raise
finally:
    save()
print(json.dumps({k: v for k, v in record.items() if k != 'steps'}, indent=2))
