#!/usr/bin/env python3
"""Check the early RAM console against a real QEMU kernel panic and RAM dump."""
import argparse
import json
from pathlib import Path
import socket
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--framebuffer', action='store_true')
parser.add_argument('--pause-rows', type=int, default=0)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
OUT = args.output or ROOT / ('out/earlyfb-qemu' if args.framebuffer else 'out/earlyram-qemu')
OUT = OUT.resolve()
OUT.mkdir(exist_ok=True)
dtb = OUT / 'virt.dtb'
monitor = OUT / 'monitor.sock'
dump = OUT / 'ram-page.bin'
monitor.unlink(missing_ok=True)
dump.unlink(missing_ok=True)
base = ['qemu-system-aarch64', '-machine', 'virt', '-cpu', 'max', '-m', '1024', '-smp', '2']
subprocess.run(base + ['-machine', f'dumpdtb={dtb}', '-display', 'none'], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
subprocess.run(['fdtput', '-c', str(dtb), '/reserved-memory'], check=True)
for key, value in [('#address-cells', ['2']), ('#size-cells', ['2']), ('ranges', [])]:
    subprocess.run(['fdtput', '-t', 'x', str(dtb), '/reserved-memory', key] + value, check=True)
node = '/reserved-memory/earlyram@60000000'
subprocess.run(['fdtput', '-c', str(dtb), node], check=True)
subprocess.run(['fdtput', '-t', 'x', str(dtb), node, 'reg', '0', '60000000', '0', '400000'], check=True)
subprocess.run(['fdtput', str(dtb), node, 'no-map'], check=True)
fb_option = 'qemu' + (f'-hold{args.pause_rows}' if args.pause_rows else '')
cmdline = ((f'earlycon=tb378fb,{fb_option} ' if args.framebuffer else 'earlycon=tb378ram,mmio,0x60000000 ')
           + 'keep_bootcon ignore_loglevel '
           'root=/dev/doesnotexist panic=0 initcall_debug')
dump_size = 1024 * 768 * 4 if args.framebuffer else 4096
with (OUT / 'qemu-output.txt').open('wb') as output:
    began = time.monotonic()
    proc = subprocess.Popen(base + ['-dtb', str(dtb), '-display', 'none', '-serial', f'file:{OUT / "serial.log"}',
        '-device', 'virtio-rng-device',
        '-monitor', f'unix:{monitor},server=on,wait=off',
        '-kernel', str(ROOT / 'out/kernel-stage1/arch/arm64/boot/Image'), '-append', cmdline],
        stdout=output, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 45
        serial_log = OUT / 'serial.log'
        while time.monotonic() < deadline:
            if serial_log.exists() and b'Kernel panic - not syncing:' in serial_log.read_bytes():
                time.sleep(1)
                break
            assert proc.poll() is None, 'QEMU exited before diagnostic capture'
            time.sleep(0.5)
        assert proc.poll() is None, 'QEMU exited before diagnostic capture'
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(3)
            sock.connect(str(monitor))
            sock.recv(8192)
            sock.sendall(f'pmemsave 0x60000000 {dump_size} "{dump}"\n'.encode())
            deadline = time.monotonic() + 5
            response = bytearray()
            while time.monotonic() < deadline:
                if dump.exists() and dump.stat().st_size == dump_size:
                    break
                try:
                    response.extend(sock.recv(65536))
                except socket.timeout:
                    pass
            (OUT / 'monitor-response.txt').write_bytes(response)
            assert dump.exists() and dump.stat().st_size == dump_size, 'RAM dump failed'
        proc.terminate()
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
raw = dump.read_bytes()
if args.framebuffer:
    white = raw.count(b'\xff\xff\xff\x00')
    black = raw.count(b'\x00\x00\x00\x00')
    assert white > 1000 and black > 1000, 'Framebuffer console did not render text'
    assert b'Kernel panic - not syncing:' in serial_log.read_bytes()
    elapsed = time.monotonic() - began
    if args.pause_rows:
        assert elapsed >= 8, 'Requested screen hold did not delay boot'
    result = {'status': 'PASSED', 'white_pixels': white, 'black_pixels': black,
              'width': 1024, 'height': 768, 'format': 'BGRX8888',
              'pause_rows': args.pause_rows, 'elapsed_seconds': round(elapsed, 2),
              'checks': ['real early console rendering', 'deliberate kernel panic', 'framebuffer RAM dump']}
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(0)
signature, start, size = struct.unpack_from('<III', raw)
assert signature == 0x43474244 and 0 <= start <= size <= 4084
# This is the same old-buffer ordering used by persistent_ram_save_old().
text = (raw[12 + start:12 + size] + raw[12:12 + start]).decode('utf-8', 'replace')
(OUT / 'recovered-console.txt').write_text(text)
assert 'Kernel panic - not syncing:' in text, 'Early console did not capture the deliberate panic'
result = {'status': 'PASSED', 'signature': hex(signature), 'start': start, 'size': size,
          'checks': ['reserved QEMU RAM page', 'real earlycon output', 'wraparound recovery', 'deliberate kernel panic']}
(OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
