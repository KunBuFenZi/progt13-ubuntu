#!/usr/bin/env python3
"""Own one native torch with a fixed current and a 30-second deadline."""
import json
import os
from pathlib import Path
import signal
import socket
import struct
import time

led = Path('/sys/class/leds/white:flash:tb378fc')
assert int((led/'max_brightness').read_text()) == 255
assert int((led/'max_flash_brightness').read_text()) == 200000
assert int(os.environ.get('LISTEN_PID','0')) == os.getpid()
assert os.environ.get('LISTEN_FDS') == '1'
server = socket.socket(fileno=3)
server.settimeout(0.25)
deadline = None
running = True

def write(name, value):
    (led/name).write_text(str(value)+'\n')

def settle(state):
    until = time.monotonic()+0.5
    while int((led/'flash_strobe').read_text()) != state:
        if time.monotonic() >= until:
            raise TimeoutError('Torch did not settle')
        time.sleep(0.005)

def off():
    global deadline
    write('brightness',0)
    settle(0)
    write('flash_strobe',0)
    deadline = None

def stop(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
off()
try:
    while running:
        if deadline is not None and time.monotonic() >= deadline:
            off()
        try:
            connection,_ = server.accept()
        except socket.timeout:
            continue
        with connection:
            connection.settimeout(0.5)
            try:
                _,uid,_ = struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if uid not in (0,1000):
                    raise PermissionError('Local desktop user required')
                request = json.loads(connection.recv(1024))
                operation = request.get('op')
                if operation == 'toggle':
                    operation = 'off' if deadline is not None else 'on'
                if operation == 'off':
                    off()
                elif operation == 'on':
                    # This board's DT caps total torch current at100mA.
                    deadline = time.monotonic()+30
                    write('brightness',255)
                    settle(1)
                elif operation != 'state':
                    raise ValueError('Unknown operation')
                response = {'on': deadline is not None,
                            'remaining': max(0,int(deadline-time.monotonic())+1) if deadline else 0}
            except Exception:
                off()
                response = {'error':'Torch unavailable'}
            try:
                connection.sendall(json.dumps(response).encode()+b'\n')
            except OSError:
                pass
finally:
    off()
    server.close()
