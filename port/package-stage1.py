#!/usr/bin/env python3
"""Package and read back a temporary TB378FC Android header-v2 candidate."""
import hashlib
import argparse
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'out/boot-stage1'
CMDLINE = ('rdinit=/init panic=15 mem_sleep_default=s2idle '
           'loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dtb', type=Path, default=ROOT / 'out/abl-stage1/erhai-abl.dtb')
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--extra-cmdline', default='', help='Diagnostic kernel options appended to the baseline')
    parser.add_argument('--kernel', type=Path, default=ROOT / 'out/kernel-stage1/arch/arm64/boot/Image')
    parser.add_argument('--ramdisk', type=Path, default=ROOT / 'out/initramfs-stage1/initramfs.cpio.gz')
    parser.add_argument('--build-manifest', type=Path, default=ROOT / 'out/stage1-build.json')
    parser.add_argument('--mainline-dtb', type=Path,
                        default=ROOT / 'out/kernel-stage1/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc.dtb')
    parser.add_argument('--image-name', default='boot-tb378fc-stage1-v2.img')
    args = parser.parse_args()
    cmdline = ' '.join(part for part in (CMDLINE, args.extra_cmdline.strip()) if part)
    assert len(cmdline.encode('ascii')) < 1536, 'Kernel command line is too long'
    out = args.output.resolve()
    inputs = {
        'kernel': args.kernel.resolve(),
        'ramdisk': args.ramdisk.resolve(),
        'dtb': args.dtb.resolve(),
    }
    mkboot = ROOT / 'inputs/mkbootimg/mkbootimg.py'
    assert digest(mkboot) == '37d84b3d162e0bc62e36c1f4e1c63c85ea0caa9f29be023eb2f8efe006ad948c'
    build = json.loads(args.build_manifest.read_text())
    for name in ('kernel', 'dtb'):
        assert inputs[name].is_file()
    kernel_key = inputs['kernel'].relative_to(ROOT).as_posix()
    assert digest(inputs['kernel']) == build['files'][kernel_key]['sha256']
    abl = json.loads(inputs['dtb'].with_name('manifest.json').read_text())
    assert digest(inputs['dtb']) == abl['outputs_sha256']['erhai-abl.dtb']
    dtb_key = args.mainline_dtb.resolve().relative_to(ROOT).as_posix()
    assert digest(args.mainline_dtb) == build['files'][dtb_key]['sha256']
    assert abl['inputs_sha256']['mainline_dtb'] == build['files'][dtb_key]['sha256']
    out.mkdir(parents=True, exist_ok=True)
    assert Path(args.image_name).name == args.image_name
    boot = out / args.image_name
    assert not boot.exists(), 'Refusing to replace an existing candidate'
    subprocess.run(['python3', str(mkboot), '--header_version', '2', '--pagesize', '4096',
                    '--base', '0', '--kernel_offset', '0x00008000',
                    '--ramdisk_offset', '0x01000000', '--tags_offset', '0x00000100',
                    '--dtb_offset', '0x01f00000', '--os_version', '15.0.0',
                    '--os_patch_level', '2026-07', '--cmdline', cmdline,
                    *[v for k, p in inputs.items() for v in ('--' + k, str(p))],
                    '--output', str(boot)], check=True)
    data = boot.read_bytes()
    assert data[:8] == b'ANDROID!'
    assert struct.unpack_from('<I', data, 40)[0] == 2
    assert struct.unpack_from('<I', data, 36)[0] == 4096
    assert struct.unpack_from('<I', data, 1644)[0] == 1660
    readback_cmdline = (data[64:576] + data[608:1632]).split(b'\0', 1)[0].decode('ascii')
    assert readback_cmdline == cmdline, 'Command line readback differs'
    sizes = {name: struct.unpack_from('<I', data, offset)[0]
             for name, offset in [('kernel', 8), ('ramdisk', 16), ('dtb', 1648)]}
    pos = 4096
    for name, path in inputs.items():
        raw = path.read_bytes()
        assert sizes[name] == len(raw)
        assert data[pos:pos + len(raw)] == raw, f'{name} readback differs'
        pos += (len(raw) + 4095) // 4096 * 4096
    assert pos == len(data) and len(data) <= 96 * 1024 * 1024
    manifest = {'status': 'OFFLINE_CANDIDATE_NOT_DEVICE_TESTED',
                'board': 'lenovo,tb378fc', 'kernel_commit': build['kernel_commit'],
                'header_version': 2, 'cmdline': cmdline,
                'abl_root_identity': abl['root_identity'],
                'scope': 'fastboot boot, temporary RAM diagnostics only',
                'inputs': {k: {'sha256': digest(p), 'size': p.stat().st_size}
                           for k, p in inputs.items()},
                'boot_sha256': digest(boot), 'boot_size': len(data),
                'checks': ['header readback', 'all components byte-identical',
                           'partition capacity', 'pinned mkbootimg']}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
