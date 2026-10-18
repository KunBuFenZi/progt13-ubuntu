#!/usr/bin/env python3
"""Build the RAM-only diagnostic archive using the kernel's newc generator."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import argparse

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'out/initramfs-stage1'
BUSYBOX = ROOT / 'inputs/busybox-root/usr/bin/busybox'
GEN = ROOT / 'out/kernel-stage1/usr/gen_init_cpio'
EXPECTED = '52151e7f322f926b64049cdaa1410dc3ea6485525e0624b05813791c219ae933'
APPS = ('sh mount mkdir cat uname sleep watchdog reboot dmesg httpd telnetd '
        'getty ip ln touch ls ps grep head tail hexdump readlink sync').split()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--kms-test', type=Path)
    parser.add_argument('--touch-firmware', type=Path,
                        help='Include this board\'s extracted volatile touchscreen firmware')
    parser.add_argument('--gpu-firmware-dir',type=Path)
    parser.add_argument('--wifi-firmware-dir',type=Path)
    parser.add_argument('--adsp-firmware-dir',type=Path)
    parser.add_argument('--amp-firmware',type=Path)
    parser.add_argument('--audio-runtime-dir','--runtime-dir',dest='audio_runtime_dir',type=Path)
    parser.add_argument('--audio-topology',type=Path)
    parser.add_argument('--gpu-test',type=Path)
    parser.add_argument('--init-script',type=Path,default=ROOT / 'port/ram-init')
    parser.add_argument('--extra-applets',default='')
    args = parser.parse_args()
    OUT = args.output.resolve()
    APPS.extend(args.extra_applets.split())
    OUT.mkdir(parents=True, exist_ok=True)
    binary = BUSYBOX.read_bytes()
    assert sha(binary) == EXPECTED, 'BusyBox digest mismatch'
    assert binary[:6] == b'\x7fELF\x02\x01'
    assert struct.unpack_from('<H', binary, 18)[0] == 183, 'Not AArch64'
    # A static executable must have no PT_INTERP.
    phoff = struct.unpack_from('<Q', binary, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', binary, 54)
    assert all(struct.unpack_from('<I', binary, phoff + i * phsize)[0] != 3
               for i in range(phnum)), 'BusyBox requires a dynamic loader'
    applets = subprocess.check_output(['qemu-aarch64', str(BUSYBOX), '--list'],
                                     timeout=20, text=True).splitlines()
    assert set(APPS + ['udhcpd']) <= set(applets), 'Missing BusyBox applets'
    sources = {}
    for name in ('ram-init', 'usb-diag'):
        script = args.init_script if name == 'ram-init' else ROOT / 'port' / name
        data = script.read_bytes()
        assert b'\r' not in data, 'Scripts must use LF'
        subprocess.run(['sh', '-n', str(script)], check=True)
        subprocess.run(['qemu-aarch64', str(BUSYBOX), 'sh', '-n',
                        str(script)], check=True, timeout=20)
        sources[name] = sha(data)
    if args.kms_test:
        kms = args.kms_test.resolve().read_bytes()
        assert kms[:6] == b'\x7fELF\x02\x01'
        assert struct.unpack_from('<H', kms, 18)[0] == 183
        phoff = struct.unpack_from('<Q', kms, 32)[0]
        phsize, phnum = struct.unpack_from('<HH', kms, 54)
        assert all(struct.unpack_from('<I', kms, phoff + i * phsize)[0] != 3
                   for i in range(phnum)), 'KMS probe requires a dynamic loader'
        sources['kms-test'] = sha(kms)
    if args.touch_firmware:
        firmware = args.touch_firmware.resolve().read_bytes()
        assert len(firmware) == 253952, 'Unexpected TB378FC firmware length'
        assert sha(firmware) == 'cf56ed4a449e34e31415f3f739685cbc4b072022f142910bfd22b4a132a2ef02', 'Not the captured TB378FC firmware'
        sources['novatek/tb378fc.bin'] = sha(firmware)
    gpu_files = {}
    if args.gpu_firmware_dir:
        directory = args.gpu_firmware_dir.resolve()
        recorded = json.loads((directory / 'manifest.json').read_text())
        for name in ('gen80000_aqe.fw','gen80000_gmu.bin','gen80000_sqe.fw','gen80000_zap.mbn'):
            path = directory / name
            assert sha(path.read_bytes()) == recorded[name]['sha256']
            destination = 'qcom/sm8750/tb378fc/'+name if name.endswith('.mbn') else 'qcom/'+name
            gpu_files[destination] = path
            sources[destination] = recorded[name]['sha256']
    if args.gpu_test:
        data = args.gpu_test.resolve().read_bytes()
        assert data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0] == 183
        phoff = struct.unpack_from('<Q',data,32)[0]
        phsize,phnum = struct.unpack_from('<HH',data,54)
        assert all(struct.unpack_from('<I',data,phoff+i*phsize)[0] != 3 for i in range(phnum))
        sources['gpu-info'] = sha(data)
    wifi_files={}
    if args.wifi_firmware_dir:
        directory=args.wifi_firmware_dir.resolve()
        manifest=json.loads((directory/'manifest.json').read_text())
        expected={'ath12k/WCN7860/hw2.0/'+name for name in
                  ('amss.bin','m3.bin','aux_ucode.bin','board.bin','regdb.bin','qdss.cfg')}
        assert set(manifest['files'])==expected
        assert manifest['hardware']=='WCN7860 hw2.0' and manifest['qmi_board_id']==255
        for name,record in manifest['files'].items():
            path=directory/name
            assert sha(path.read_bytes())==record['sha256']
            assert path.stat().st_size==record['size']
            wifi_files[name]=path;sources[name]=record['sha256']
        # cfg80211 loads its signed database before switch-root. Keep the
        # database and signature from the verified Ubuntu root available then.
        for name in ('regulatory.db','regulatory.db.p7s'):
            path=ROOT/'out/desktop-root/usr/lib/firmware'/name
            assert path.is_file() and not path.is_symlink()
            wifi_files[name]=path;sources[name]=sha(path.read_bytes())
    adsp_files={}
    if args.adsp_firmware_dir:
        directory=args.adsp_firmware_dir.resolve()
        manifest=json.loads((directory/'manifest.json').read_text())
        assert len(manifest['files'])==62
        assert {'adsp.mdt','adsp_dtb.mdt'}<=manifest['files'].keys()
        for name,record in manifest['files'].items():
            assert Path(name).name==name and name.startswith(('adsp.','adsp_dtb.'))
            path=directory/name
            assert sha(path.read_bytes())==record['sha256'] and path.stat().st_size==record['size']
            destination='qcom/sm8750/tb378fc/'+name
            adsp_files[destination]=path;sources[destination]=record['sha256']
    if args.amp_firmware:
        amp = args.amp_firmware.resolve()
        proof = json.loads(amp.with_name('manifest.json').read_text())
        assert sha(amp.read_bytes()) == proof['output_sha256']
        sources['awinic/tb378fc/aw88480-native-music.acf'] = proof['output_sha256']
    audio_files = {}
    if args.audio_runtime_dir:
        directory = args.audio_runtime_dir.resolve()
        manifest = json.loads((directory/'manifest.json').read_text())
        for name, record in manifest['files'].items():
            assert name and not Path(name).is_absolute() and '..' not in Path(name).parts
            assert all(c not in name for c in (' ', '\n', '\\'))
            path = (directory/name).resolve()
            assert path.is_relative_to(directory) and path.is_file()
            assert sha(path.read_bytes()) == record['sha256']
            assert record['mode'] in (0o644, 0o755)
            assert name not in {'bin/'+app for app in APPS+['busybox','usb-diag','udhcpd']}
            audio_files[name] = (path, record['mode'])
            sources['audio-runtime/'+name] = record['sha256']
    if args.audio_topology:
        path = args.audio_topology.resolve()
        assert path.read_bytes()[:4] == b'CoSA', 'Invalid ALSA topology magic'
        name = 'lib/firmware/qcom/sm8750/Lenovo-TB378FC-tplg.bin'
        audio_files[name] = (path, 0o644)
        sources[name] = sha(path.read_bytes())
    build_id = sha(json.dumps({'busybox': EXPECTED, 'scripts': sources,
                              'applets': APPS}, sort_keys=True).encode())
    (OUT / 'build-id').write_text(build_id + '\n')
    lines = [f'dir /{name} 0755 0 0' for name in ('', 'bin', 'dev', 'proc', 'sys', 'run', 'etc')]
    lines += ['nod /dev/console 0600 0 0 c 5 1', 'nod /dev/null 0666 0 0 c 1 3',
              f'file /bin/busybox {BUSYBOX} 0755 0 0',
              f'file /init {args.init_script.resolve()} 0755 0 0',
              f'file /bin/usb-diag {ROOT}/port/usb-diag 0755 0 0',
              f'file /etc/build-id {OUT}/build-id 0644 0 0']
    lines += [f'slink /bin/{app} busybox 0777 0 0' for app in APPS]
    # Ubuntu's static BusyBox does not necessarily include udhcpd: build fails
    # during applet validation if this network service is missing.
    lines += ['slink /bin/udhcpd busybox 0777 0 0']
    if args.kms_test:
        lines += [f'file /bin/kms-test {args.kms_test.resolve()} 0755 0 0']
    if args.touch_firmware:
        lines += ['dir /lib 0755 0 0', 'dir /lib/firmware 0755 0 0',
                  'dir /lib/firmware/novatek 0755 0 0',
                  f'file /lib/firmware/novatek/tb378fc.bin {args.touch_firmware.resolve()} 0644 0 0']
    if gpu_files:
        if not args.touch_firmware:
            lines += ['dir /lib 0755 0 0','dir /lib/firmware 0755 0 0']
        lines += [f'dir /lib/firmware/{d} 0755 0 0' for d in ('qcom','qcom/sm8750','qcom/sm8750/tb378fc')]
        lines += [f'file /lib/firmware/{d} {p} 0644 0 0' for d,p in gpu_files.items()]
    if args.gpu_test:
        lines += [f'file /bin/gpu-info {args.gpu_test.resolve()} 0755 0 0']
    if wifi_files:
        if not args.touch_firmware and not gpu_files:
            lines += ['dir /lib 0755 0 0','dir /lib/firmware 0755 0 0']
        lines += [f'dir /lib/firmware/{name} 0755 0 0' for name in
                  ('ath12k','ath12k/WCN7860','ath12k/WCN7860/hw2.0')]
        lines += [f'file /lib/firmware/{name} {path} 0644 0 0' for name,path in wifi_files.items()]
    if adsp_files:
        if not args.touch_firmware and not gpu_files and not wifi_files:
            lines += ['dir /lib 0755 0 0','dir /lib/firmware 0755 0 0']
        if not gpu_files:
            lines += [f'dir /lib/firmware/{d} 0755 0 0' for d in ('qcom','qcom/sm8750','qcom/sm8750/tb378fc')]
        lines += [f'file /lib/firmware/{name} {path} 0644 0 0' for name,path in adsp_files.items()]
    if args.amp_firmware:
        if not any((args.touch_firmware, gpu_files, wifi_files, adsp_files)):
            lines += ['dir /lib 0755 0 0','dir /lib/firmware 0755 0 0']
        lines += ['dir /lib/firmware/awinic 0755 0 0',
                  'dir /lib/firmware/awinic/tb378fc 0755 0 0',
                  f'file /lib/firmware/awinic/tb378fc/aw88480-native-music.acf {args.amp_firmware.resolve()} 0644 0 0']
    for name, (path, mode) in audio_files.items():
        for parent in reversed(Path(name).parents):
            if str(parent) != '.':
                lines.append(f'dir /{parent.as_posix()} 0755 0 0')
        lines.append(f'file /{name} {path} {mode:04o} 0 0')
    # Firmware and dynamic runtime share parent directories. Emit each path once.
    unique = {}
    for line in lines:
        destination = line.split()[1]
        assert destination not in unique or unique[destination] == line, destination
        unique[destination] = line
    lines = list(unique.values())
    (OUT / 'cpio-list.txt').write_text('\n'.join(lines) + '\n')
    raw = subprocess.check_output([str(GEN), '-t', '0', str(OUT / 'cpio-list.txt')])
    archive = gzip.compress(raw, mtime=0)
    (OUT / 'initramfs.cpio.gz').write_bytes(archive)
    listing = subprocess.run(['cpio', '-itv'], input=raw, capture_output=True, check=True)
    (OUT / 'archive-list.txt').write_bytes(listing.stdout)
    manifest = {'status': 'OFFLINE_NOT_BOOT_TESTED', 'build_id': build_id,
                'busybox_sha256': EXPECTED, 'scripts_sha256': sources,
                'cpio_sha256': sha(raw), 'gzip_sha256': sha(archive),
                'gzip_size': len(archive), 'init_script':str(args.init_script),
                'timeout_seconds': 180 if args.init_script.name == 'ram-init' else None}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
