#!/usr/bin/env python3
"""Supplement missing 5GHz discovery through the running supplicant.

Ordinary mixed scans miss high-band results on the current native firmware.
Refresh known/common channels and retain partial results across the other
channel scans, so a discovered network stays selectable in NM's menu.
No country override, connection credentials or firmware reload is involved.
"""
from pathlib import Path
import argparse
import re
import subprocess
import time
from gi.repository import Gio, GLib

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--force',action='store_true',help='Request a diagnostic scan even with cached 5GHz results')
args=parser.parse_args()

interfaces=[p.name for p in Path('/sys/class/net').iterdir() if (p/'wireless').is_dir()]
if len(interfaces)!=1:raise SystemExit(0)
iface=interfaces[0]
known=subprocess.run(['nmcli','-t','-f','FREQ','device','wifi','list',
                      'ifname',iface,'--rescan','no'],capture_output=True,text=True,timeout=5)
visible={int(float(f)) for f in re.findall(r'(\d+(?:\.\d+)?) MHz',known.stdout)
         if 4900<float(f)<5925}
stamp=Path('/run/tb378fc-passive5-last')
last=float(stamp.read_text()) if stamp.exists() else -1000
phy=(Path('/sys/class/net')/iface/'phy80211').resolve().name
info=subprocess.run(['iw','phy',phy,'info'],capture_output=True,text=True,check=True,timeout=5)
channels=[]
for line in info.stdout.splitlines():
    match=re.search(r'\* (\d+(?:\.\d+)?) MHz \[\d+\]',line)
    if match and 'disabled' not in line and 4900<float(match[1])<5925:
        channels.append((int(float(match[1])),0))
if not channels:raise SystemExit(0)
cursor_file=Path('/run/tb378fc-passive5-cursor')
common={5180,5200,5220,5240,5745,5765,5785,5805,5825}
priority=[c for c in channels if c[0] in common|visible]
others=[c for c in channels if c not in priority]
cursor=int(cursor_file.read_text())%len(others) if others and cursor_file.exists() else 0
requests=[(c,False) for c in priority]
if others:
    requests += [(others[(cursor+i)%len(others)],True) for i in range(min(4,len(others)))]
bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
dest='fi.w1.wpa_supplicant1'
try:
    path=bus.call_sync(dest,'/fi/w1/wpa_supplicant1',dest,'GetInterface',
        GLib.Variant('(s)',(iface,)),GLib.VariantType.new('(o)'),
        Gio.DBusCallFlags.NONE,5000,None).unpack()[0]
    def get_property(name):
        return bus.call_sync(dest,path,'org.freedesktop.DBus.Properties','Get',
            GLib.Variant('(ss)',(dest+'.Interface',name)),None,
            Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
    # The default count of two discards useful results during our partial scans.
    # Preserve the normal age limit; keep each known channel fresh below it.
    bus.call_sync(dest,path,'org.freedesktop.DBus.Properties','Set',
        GLib.Variant('(ssv)',(dest+'.Interface','BSSExpireCount',GLib.Variant('u',64))),
        None,Gio.DBusCallFlags.NONE,3000,None)
    if not args.force and get_property('State')=='completed' and time.monotonic()-last<30:
        print('CONNECTED_DISCOVERY_RECENT');raise SystemExit(0)
    deadline=time.monotonic()+24
    for channel,extra in requests:
        while True:
            state=get_property('State')
            if state not in ('disconnected','inactive','completed','scanning'):
                print('PASSIVE_DISCOVERY_LEFT_TO_CONNECTION',state);raise SystemExit(0)
            scanning=get_property('Scanning')
            if not scanning:break
            if time.monotonic()>=deadline:
                print('PASSIVE_DISCOVERY_WAITING_FOR_NETWORKMANAGER');raise SystemExit(0)
            time.sleep(.25)
        if time.monotonic()>=deadline:break
        loop=GLib.MainLoop()
        result={'success':None,'timed_out':False}
        def finished(connection,sender,object_path,interface,name,parameters,data):
            result['success']=parameters.unpack()[0];loop.quit()
        def timeout():
            result['timed_out']=True;loop.quit();return False
        subscription=bus.signal_subscribe(dest,dest+'.Interface','ScanDone',path,
            None,Gio.DBusSignalFlags.NONE,finished,None)
        timeout_id=None
        try:
            frequency=channel[0]
            options={'Type':GLib.Variant('s','passive'),
                     'Channels':GLib.Variant('a(uu)',[channel])}
            bus.call_sync(dest,path,dest+'.Interface','Scan',GLib.Variant('(a{sv})',(options,)),
                None,Gio.DBusCallFlags.NONE,5000,None)
            timeout_id=GLib.timeout_add(5000,timeout)
            loop.run()
        finally:
            bus.signal_unsubscribe(subscription)
            if timeout_id is not None and not result['timed_out']:GLib.source_remove(timeout_id)
        print('PASSIVE_CHANNEL',frequency,'complete',result['success'],flush=True)
        if result['timed_out']:break
        if extra:
            cursor=(cursor+1)%len(others)
            cursor_file.write_text(str(cursor)+'\n')
    stamp.write_text(str(time.monotonic())+'\n')
except GLib.Error as exc:
    # NM owns the device: an in-progress scan/association is simply left alone.
    print('SUPPLICANT_SCAN_DEFERRED',exc.message)
