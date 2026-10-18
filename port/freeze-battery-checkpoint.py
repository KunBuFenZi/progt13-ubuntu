#!/usr/bin/env python3
"""Freeze exact battery-desktop inputs and reviewed, secret-free acceptance proof."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile

root = Path(__file__).resolve().parent.parent
os.chdir(root)
dest = Path('out/checkpoint-battery-desktop-good')
assert not dest.exists()
evidence = Path('out/validated-evidence/attempt39')
battery = json.loads((evidence/'battery-ui-proof.json').read_text())
init = json.loads(Path('out/initramfs-battery-desktop-v8/manifest.json').read_text())
boot = json.loads(Path('out/boot-battery-desktop-v8/manifest.json').read_text())
assert battery['build_id'] == init['build_id']
assert battery['invalid_power_hidden'] and battery['native']['current_now'] < 0
assert battery['display']['State'] == 2 and battery['display']['WarningLevel'] == 1
network = json.loads((evidence/'network-proof.json').read_text())
assert '160MHz EHT-' in network['link'] and 'SSID: TEST_WIFI' in network['link']
assert all(x.get('status') == 200 and x.get('bytes') == 8388608 for x in network['transfers'])
render = (evidence/'render-hardware.txt').read_text()
assert 'triangle_pixel_verified' in render and 'PROBE_EXIT=0' in render and '830v1' in render

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

image = 'out/boot-battery-desktop-v8/boot-tb378fc-battery-desktop-v8.img'
assert digest(image) == boot['boot_sha256']
dest.mkdir()
shutil.copytree(evidence, dest/'evidence')
shutil.copy2('out/battery-probe-v3/settings-v8.tar', dest/'settings.tar')
sources = ['port/sm8750-lenovo-tb378fc-battery.dts','port/sm8750-lenovo-tb378fc-adsp.dts',
           'port/prepare-adsp.py','port/fix-lenovo-battery.py','port/build-battery.sh',
           'port/build-battery-probe.py','port/package-battery-desktop.py',
           'port/prepare-desktop-settings.py','port/wifi-passive-discovery.py',
           'port/volume-orientation.py','port/freeze-battery-checkpoint.py',
           'tools/verify-battery-ui.py','out/battery-native-v2.patch']
with tarfile.open(dest/'sources.tar','w') as tar:
    for name in sources:
        tar.add(name, arcname=name)
refs = [image,'out/boot-battery-desktop-v8/manifest.json',
        'out/initramfs-battery-desktop-v8/initramfs.cpio.gz',
        'out/initramfs-battery-desktop-v8/manifest.json',
        'out/kernel-battery-v2/arch/arm64/boot/Image','out/kernel-battery-v2/.config',
        'out/battery-probe-v3/sm8750-lenovo-tb378fc-battery.dtb',
        'out/battery-probe-v3/abl/erhai-abl.dtb','out/battery-v2-build.json']
manifest = {'status': 'GNOME_GPU_WIFI7_BATTERY_COLD_BOOT_VERIFIED_RAM_ONLY',
            'build_id': init['build_id'], 'boot_sha256': boot['boot_sha256'],
            'references': {name: digest(name) for name in refs},
            'files': {p.relative_to(dest).as_posix(): digest(p)
                      for p in dest.rglob('*') if p.is_file()},
            'limits': ['No system suspend, fast charging, 6GHz/MLO or long-duration acceptance',
                       'CPU7, audio, Bluetooth and sensors still incomplete',
                       'No partition writes or persistent installation'],
            'credentials': 'No Wi-Fi password or client private key included'}
(dest/'checkpoint.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'status': manifest['status'], 'boot_sha256': boot['boot_sha256']}))
