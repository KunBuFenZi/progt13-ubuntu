#!/usr/bin/env python3
"""Route only TB378FC's two native volume keys for the GNOME display rotation.

Natural landscape: GPIO6 is left (decrease), RESIN right (increase), as
reported on this device. Portrait mapping remains physically unverified.
External keyboards, touch, pen and the power key are never grabbed.
"""
import fcntl
import contextlib
import glob
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import time

EVENT=struct.Struct('@llHHi')
KEYS={114,115}
NAME='TB378FC oriented volume'

def watch_display():
    # One unprivileged DBus connection; no repeated PAM sessions or subprocesses.
    from gi.repository import Gio, GLib
    proxy=Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION,
        Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,None,'org.gnome.Mutter.DisplayConfig',
        '/org/gnome/Mutter/DisplayConfig','org.gnome.Mutter.DisplayConfig',None)
    def publish(*_):
        try:
            state=proxy.call_sync('GetCurrentState',None,Gio.DBusCallFlags.NONE,8000,None).unpack()
            primary=[m for m in state[2] if m[4]]
            if len(primary)!=1 or primary[0][3] not in range(4):
                raise RuntimeError('Unsupported primary display layout')
            print(primary[0][3],flush=True)
        except GLib.Error as exc:
            print('Display query deferred: '+exc.message,file=sys.stderr,flush=True)
        return True
    proxy.connect('g-signal',lambda p,s,n,a:publish() if n=='MonitorsChanged' else None)
    publish()
    GLib.timeout_add_seconds(5,publish)
    GLib.MainLoop().run()

def devices():
    found={}
    for path in glob.glob('/sys/class/input/event*'):
        root=Path(path)/'device'
        name=(root/'name').read_text().strip()
        if name not in ('gpio-keys','pmic_resin'):
            continue
        code=115 if name=='gpio-keys' else 114
        # This board's native devices expose exactly one key each.
        words=(root/'capabilities/key').read_text().split()
        bits=sum(int(word,16)<<(i*struct.calcsize('@L')*8)
                 for i,word in enumerate(reversed(words)))
        if bits!=1<<code or name in found:
            for fd in found.values():os.close(fd)
            raise RuntimeError('Native volume device layout changed')
        found[name]=os.open('/dev/input/'+Path(path).name,os.O_RDONLY|os.O_NONBLOCK)
    if len(found)!=2:
        for fd in found.values():os.close(fd)
        raise RuntimeError('Both native volume keys must be available')
    return found

def emit(fd,code,value):
    os.write(fd,EVENT.pack(0,0,1,code,value)+EVENT.pack(0,0,0,0,0))

def main():
    compatible=Path('/proc/device-tree/compatible').read_bytes().split(b'\0')
    # ABL replaces the root compatible/model with its Qualcomm identity.
    native=any(b'lenovo,tb378fc-' in p.read_bytes()
               for p in Path('/proc/device-tree').rglob('compatible'))
    if b'lenovo,tb378fc' not in compatible and not native:
        raise RuntimeError('Unexpected board')
    with contextlib.ExitStack() as resources:
        route_keys(resources)

def stop_watcher(watcher):
    if watcher.poll() is None:watcher.terminate()
    try:watcher.wait(timeout=3)
    except subprocess.TimeoutExpired:
        watcher.kill();watcher.wait(timeout=3)

def route_keys(resources):
    watcher=subprocess.Popen([sys.executable,__file__,'--watch-display'],stdout=subprocess.PIPE,
        env=dict(os.environ,DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus',
                 XDG_RUNTIME_DIR='/run/user/1000'),user=1000,group=1000,extra_groups=[])
    resources.callback(stop_watcher,watcher)
    if not select.select([watcher.stdout],[],[],15)[0]:
        raise RuntimeError('GNOME display state unavailable')
    transform=int(watcher.stdout.readline().strip())
    if transform not in range(4):raise RuntimeError('Unsupported display transform')
    os.set_blocking(watcher.stdout.fileno(),False)
    sources=devices()
    for fd in sources.values():resources.callback(os.close,fd)
    virtual=os.open('/dev/uinput',os.O_WRONLY|os.O_NONBLOCK)
    resources.callback(os.close,virtual)
    held={}
    try:
        fcntl.ioctl(virtual,0x40045564,1) # UI_SET_EVBIT EV_KEY
        for code in KEYS:fcntl.ioctl(virtual,0x40045565,code)
        setup=struct.pack('HHHH80sI',3,0x17ef,0x378f,1,NAME.encode(),0)
        fcntl.ioctl(virtual,0x405c5503,setup)
        fcntl.ioctl(virtual,0x5501) # UI_DEV_CREATE
        time.sleep(0.5)
        for fd in sources.values():fcntl.ioctl(fd,0x40044590,1) # EVIOCGRAB
        print('VOLUME_PROXY_READY transform='+str(transform),flush=True)
        refreshed=time.monotonic()
        pending=b''
        while True:
            if watcher.poll() is not None or time.monotonic()-refreshed>45:
                raise RuntimeError('Display watcher lost; releasing native keys')
            ready,_,_=select.select([*sources.values(),watcher.stdout.fileno()],[],[],0.25)
            for fd in ready:
                if fd==watcher.stdout.fileno():
                    data=os.read(fd,4096)
                    if not data:raise RuntimeError('Display watcher disconnected')
                    pending+=data
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1)
                        new=int(line)
                        if new not in range(4):raise RuntimeError('Unsupported transform')
                        if new!=transform:print('DISPLAY_TRANSFORM '+str(new),flush=True)
                        transform=new;refreshed=time.monotonic()
                    continue
                data=os.read(fd,EVENT.size*32)
                if not data or len(data)%EVENT.size:raise RuntimeError('Input disconnected')
                for _,_,kind,code,value in EVENT.iter_unpack(data):
                    if kind==0 and code==3:raise RuntimeError('Input stream overflow')
                    if kind!=1 or code not in KEYS:continue
                    key=(fd,code)
                    if value==1:
                        held[key]=229-code if transform in (0,3) else code
                    mapped=held.get(key)
                    if mapped is not None:emit(virtual,mapped,value)
                    if value==0:held.pop(key,None)
    finally:
        for mapped in held.values():
            with contextlib.suppress(OSError):emit(virtual,mapped,0)
        with contextlib.suppress(OSError):fcntl.ioctl(virtual,0x5502) # UI_DEV_DESTROY
        # ExitStack closes all evdev handles (releasing their grabs), the
        # virtual device and watcher even after setup or cleanup failures.

if __name__=='__main__':
    def stop(*_):raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    if sys.argv[1:]==['--watch-display']:watch_display()
    else:main()
