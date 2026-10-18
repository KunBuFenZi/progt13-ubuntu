#!/usr/bin/env python3
"""Prepare a 120-Hz RAM recovery image with the already tested camera/mic fixes."""
import copy
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parent.parent
os.chdir(root)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', default='75b')
args = parser.parse_args()
assert args.revision in ['75b']
revision = args.revision
work = root / ('out/runtime-recovery' + revision)
work.mkdir(exist_ok=False)
private = root / 'out/private75'
private.mkdir(exist_ok=True)
private.chmod(0o700)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
base = root / 'out/private74/settings-camera74.tar'
assert sha(base) == 'b8fab9e6c27f2c29e7eb277c376d7fd254cc97d3d39c2af191bb4c5b4a80bb81'
entries = {}
with tarfile.open(base) as archive:
    for item in archive:
        entries[item.name] = (copy.copy(item), archive.extractfile(item).read() if item.isfile() else None)


def add(name, data, mode=0o644):
    assert not name.startswith('/') and '..' not in Path(name).parts
    item = tarfile.TarInfo(name)
    item.mode, item.size = mode, len(data)
    entries[name] = (item, data)


with tarfile.open(root / 'out/restore75.tar.gz') as archive:
    restored = {item.name.rstrip('/'): (copy.copy(item), archive.extractfile(item).read() if item.isfile() else None)
                for item in archive}
for name, (item, data) in restored.items():
    if name.startswith(('usr/lib/tb378fc/camera75', 'usr/share/alsa/ucm2/')):
        entries[name] = (item, data)
camss = restored['run/qcom-camss75.ko'][1]
heap = restored['run/system_heap75.ko'][1]
assert hashlib.sha256(camss).hexdigest() == 'acf8707b0ba05173ec64b982ba177511e695d3021c26030c8c932f544c3a09d4'
assert hashlib.sha256(heap).hexdigest() == '3aa5a452f2252b00e9cb773aef45a7df2d925a9155fff1f60d345a170b5553a5'
prefix = 'usr/share/tb378fc/camera74/'
add(prefix + 'camss/qcom-camss.ko', camss)
add(prefix + 'heap/system_heap.ko', heap)
manifest = json.loads(entries[prefix + 'manifest.json'][1])
manifest['status'] = 'CAMERA75_R4_AND_CAMSS_ALIGNMENT_INTEGRATED_FOR_RAM_RECOVERY'
manifest['modules']['camss/qcom-camss.ko'] = json.loads((root / 'out/camera-app75/camss-manifest.json').read_text())
camss_path = work / 'qcom-camss.ko'
camss_path.write_bytes(camss)
manifest['modules']['camss/qcom-camss.ko']['exports'] = [line.split()[-1].removeprefix('__ksymtab_') for line in
    subprocess.check_output(['aarch64-linux-gnu-nm', str(camss_path)], text=True).splitlines()
    if line.split() and line.split()[-1].startswith('__ksymtab_')]
heap_path = work / 'system_heap.ko'
heap_path.write_bytes(heap)
imports = [line.split()[-1] for line in subprocess.check_output(['aarch64-linux-gnu-nm', '-u', str(heap_path)], text=True).splitlines()]
exports = [line.split()[-1].removeprefix('__ksymtab_') for line in subprocess.check_output(['aarch64-linux-gnu-nm', str(heap_path)], text=True).splitlines()
           if line.split() and line.split()[-1].startswith('__ksymtab_')]
manifest['modules']['heap/system_heap.ko'] = {'sha256': sha(heap_path), 'imports': imports, 'exports': exports,
    'vermagic': subprocess.check_output(['modinfo', '-F', 'vermagic', str(heap_path)], text=True).strip()}
add(prefix + 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
assert all({'sha256', 'imports', 'exports', 'vermagic'} <= set(item) for item in manifest['modules'].values())
helper = restored['usr/local/libexec/tb378fc-camera74.py'][1].decode()
helper = helper.replace("record['video_devices'] =", """# The CPU ISP needs the shared DMA heap; pad is already in the video group.
import grp, os
os.chown('/dev/dma_heap/system', 0, grp.getgrnam('video').gr_gid)
os.chmod('/dev/dma_heap/system', 0o660)
record['video_devices'] =""")
add('usr/local/libexec/tb378fc-camera74.py', helper.encode(), 0o755)
media = (root / 'port/camera75-media.conf').read_bytes()
for unit in ['pipewire', 'wireplumber']:
    add('etc/systemd/user/' + unit + '.service.d/95-camera75.conf', media)
add('etc/udev/rules.d/82-tb378fc-dmaheap75.rules', b'SUBSYSTEM=="dma_heap", KERNEL=="system", GROUP="video", MODE="0660"\n')
# Never include refresh hooks, extra modes, diagnostics modules or HD launchers.
assert not any(any(t in n for t in ['refresh-live75', 'refresh-hooks75', 'camera-hd75', 'camera75r7', 'apm-inspect75', 'swr-timing75']) for n in entries)
settings = private / ('settings-recovery' + revision + '.tar')
with settings.open('xb') as handle:
    settings.chmod(0o600)
    with tarfile.open(fileobj=handle, mode='w') as archive:
        for name, (item, data) in sorted(entries.items()):
            archive.addfile(item, io.BytesIO(data) if data is not None else None)

tree = root / ('out/recovery-tree' + revision)
tree.mkdir()
dtb = tree / 'sm8750-lenovo-tb378fc-recovery75.dtb'
base_dtb = root / 'out/camera-tree74/static-no-symbols.dtb'
shutil.copy2(base_dtb, dtb)
# Exactly the two idle port timing changes acoustically verified in RAM:
# ADC1 master DP3 lane1/off0, ADC3 master DP4 lane0/off2, LP interval unchanged.
for prop, values in [('qcom,ports-offset1', ['0', '0', '0', '2']),
                     ('qcom,ports-lane-control', ['1', '2', '1', '0'])]:
    subprocess.run(['fdtput', '-t', 'bx', str(dtb), '/soc@0/soundwire@7630000', prop, *values], check=True)
subprocess.run([sys.executable, 'reference-tools/build-erhai-abl-symbols.py', '--mainline-dtb', str(dtb),
                '--dtbo-img', 'inputs/dtbo.img', '--base-dir', 'inputs/stock-base', '--identity-index', '11',
                '--dtc', 'out/kernel-usbc70b/scripts/dtc/dtc', '--output', str(tree / 'abl-static')], check=True)
script = (root / 'port/desktop-init').read_text()
assert script.count('@SETTINGS_SHA@') == 1
(work / 'init').write_text(script.replace('@SETTINGS_SHA@', sha(settings)))
subprocess.run([sys.executable, 'port/build-initramfs.py', '--output', 'out/initramfs-recovery' + revision,
                '--init-script', str(work / 'init'), '--extra-applets', 'wget sha256sum tar chown switch_root tee seq kill umount cp mv',
                '--touch-firmware', 'diagnostics/firmware/novatek_ts_fw.bin', '--gpu-firmware-dir', 'diagnostics/firmware/gpu',
                '--wifi-firmware-dir', 'out/wifi-native-v2', '--adsp-firmware-dir', 'diagnostics/firmware/adsp'], check=True)
build = json.loads((root / 'out/runtime-camera74/build-manifest.json').read_text())
build.update(status='RECOVERY75_120HZ_WITH_VERIFIED_MIC_AND_CAMERA', settings_sha256=sha(settings))
build['files'][dtb.relative_to(root).as_posix()] = {'sha256': sha(dtb), 'size': dtb.stat().st_size}
(work / 'build-manifest.json').write_text(json.dumps(build, indent=2) + '\n')
cmd = json.loads((root / 'out/boot-camera74/manifest.json').read_text())['cmdline']
baseline = 'rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert cmd.startswith(baseline)
subprocess.run([sys.executable, 'port/package-stage1.py', '--kernel', 'out/kernel-usbc70b/arch/arm64/boot/Image',
                '--dtb', str(tree / 'abl-static/erhai-abl.dtb'), '--mainline-dtb', str(dtb),
                '--ramdisk', 'out/initramfs-recovery' + revision + '/initramfs.cpio.gz', '--build-manifest', str(work / 'build-manifest.json'),
                '--extra-cmdline', cmd[len(baseline):], '--output', 'out/boot-recovery' + revision,
                '--image-name', 'boot-tb378fc-recovery' + revision + '.img'], check=True)
record = {'status': 'RAM_RECOVERY75_BUILT_NOT_BOOTED', 'settings_sha256': sha(settings),
          'boot_sha256': sha(root / ('out/boot-recovery' + revision + '/boot-tb378fc-recovery' + revision + '.img')),
          'build_id': (root / ('out/initramfs-recovery' + revision + '/build-id')).read_text().strip(),
          'kernel_image_unchanged': True, 'refresh_modes': [120], 'camera_hd_entry': False,
          'camera_runtime': 'accepted r4', 'microphone': 'acoustically verified ADC1, ADC3 unverified',
          'dt_changes': ['TX SWR port3 lane1/offset0', 'TX SWR port4 lane0/offset2']}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
