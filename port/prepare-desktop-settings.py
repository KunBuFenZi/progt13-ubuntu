#!/usr/bin/env python3
"""Build a small RAM-only overlay configuration from the verified Ubuntu root."""
import hashlib
import argparse
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time

ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--wifi-firmware-dir',type=Path)
p.add_argument('--adsp-firmware-dir',type=Path)
p.add_argument('--amp-firmware',type=Path)
p.add_argument('--audio-topology',type=Path)
p.add_argument('--hold-battery-ui',action='store_true')
p.add_argument('--validated-mesa-dir',type=Path)
p.add_argument('--oriented-volume-keys',action='store_true')
p.add_argument('--zram',action='store_true')
p.add_argument('--reference-display-power',action='store_true')
p.add_argument('--usb-ssh-runtime',type=Path)
p.add_argument('--usb-ssh-public-key',type=Path)
p.add_argument('--clock-epoch',type=int,default=int(time.time()))
args=p.parse_args()
assert bool(args.usb_ssh_runtime)==bool(args.usb_ssh_public_key)
base=ROOT/'out/desktop-root'
out=ROOT/'out/desktop-serve'
out.mkdir(exist_ok=True)
files={}
mtimes={}
def add(path,data,mode=0o644):
    files[path]=(data.encode() if isinstance(data,str) else data,mode)


passwd=(base/'etc/passwd').read_text()
ssh_shadow=''
if args.usb_ssh_runtime and not any(line.startswith('sshd:') for line in passwd.splitlines()):
    used={int(line.split(':')[2]) for line in passwd.splitlines()}
    uid=next(n for n in range(990,979,-1) if n not in used)
    assert any(line.startswith('nogroup:x:65534:') for line in (base/'etc/group').read_text().splitlines())
    passwd+=f'sshd:x:{uid}:65534:OpenSSH privilege separation:/run/sshd:/usr/sbin/nologin\n'
    ssh_shadow='sshd:!:20000:0:99999:7:::\n'
assert not any(line.split(':')[2]=='1000' for line in passwd.splitlines())
add('etc/passwd',passwd+'pad:x:1000:1000:Tablet Linux:/home/pad:/bin/bash\n')
add('etc/shadow',(base/'etc/shadow').read_text()+ssh_shadow+'pad:!:20000:0:99999:7:::\n',0o640)
groups=[]
for line in (base/'etc/group').read_text().splitlines():
    parts=line.split(':')
    if parts[0] in ('video','render','input','audio'):
        parts[3]=','.join(filter(None,[parts[3],'pad']))
    groups.append(':'.join(parts))
add('etc/group','\n'.join(groups)+'\npad:x:1000:\n')
add('etc/gshadow',(base/'etc/gshadow').read_text()+'pad:!::\n',0o640)
add('etc/hostname','tb378fc-ram\n')
add('etc/hosts','127.0.0.1 localhost\n127.0.1.1 tb378fc-ram\n::1 localhost\n')
add('etc/fstab','# Diagnostic root, all writable filesystems are RAM.\n')
add('etc/machine-id','uninitialized\n')
# With no RTC driver yet, start at the known build date rather than the ISO's
# April epoch. Network time can refine it after a Wi-Fi connection is available.
add('usr/lib/clock-epoch','')
mtimes['usr/lib/clock-epoch']=args.clock_epoch
add('etc/gdm3/custom.conf','[daemon]\nAutomaticLoginEnable=true\nAutomaticLogin=pad\nDefaultSession=ubuntu.desktop\n[debug]\nEnable=true\n')
add('var/lib/AccountsService/users/pad','[User]\nSession=ubuntu\nXSession=ubuntu\nSystemAccount=false\n')
add('home/pad/.config/gnome-initial-setup-done','yes\n')
add('home/pad/.config/gnome-initial-setup/upgrade-26.04-done','yes\n')
add('home/pad/.config/monitors.xml','''<monitors version="2"><configuration><logicalmonitor><x>0</x><y>0</y><scale>2</scale><primary>yes</primary><monitor><monitorspec><connector>DSI-1</connector><vendor>unknown</vendor><product>unknown</product><serial>unknown</serial></monitorspec><mode><width>3504</width><height>2190</height><rate>120</rate></mode></monitor></logicalmonitor></configuration></monitors>\n''')
add('etc/environment','LIBGL_ALWAYS_SOFTWARE=1\nGALLIUM_DRIVER=llvmpipe\n')
# This disposable session must not exercise the unverified blank/resume path.
# Use the actual Ubuntu dconf compiler, with the same ARM64 libraries as the root.
power_defaults='''[org/gnome/desktop/session]
idle-delay=uint32 0

[org/gnome/desktop/screensaver]
lock-enabled=false

[org/gnome/settings-daemon/plugins/power]
idle-dim=false
power-button-action='nothing'
sleep-inactive-ac-type='nothing'
sleep-inactive-battery-type='nothing'
'''
add('etc/dconf/profile/user','user-db:user\nsystem-db:tb378fc\n')
add('etc/dconf/db/tb378fc.d/00-ram-trial',power_defaults)
with tempfile.TemporaryDirectory(prefix='tb378fc-dconf-') as tmp:
    tmp=Path(tmp)
    keys=tmp/'keys';keys.mkdir()
    (keys/'00-ram-trial').write_text(power_defaults)
    database=tmp/'tb378fc'
    subprocess.run(['qemu-aarch64','-L',str(base),str(base/'usr/bin/dconf'),
                    'compile',str(database),str(keys)],check=True)
    add('etc/dconf/db/tb378fc',database.read_bytes())
add('etc/systemd/system.conf.d/90-tb378fc-ram.conf','[Manager]\nRuntimeWatchdogSec=15s\nRebootWatchdogSec=30s\nDefaultTimeoutStopSec=10s\n')
add('etc/systemd/journald.conf.d/90-tb378fc-ram.conf','[Journal]\nStorage=volatile\nRuntimeMaxUse=64M\nForwardToConsole=no\n')
add('etc/systemd/logind.conf.d/90-tb378fc-ram.conf','[Login]\nHandlePowerKey=ignore\nHandleLidSwitch=ignore\nIdleAction=ignore\n')
add('usr/local/libexec/tb378fc-evidence','''#!/bin/sh
mkdir -p /run/evidence
cp /etc/tb378fc-build-id /run/evidence/build-id.txt
/usr/local/libexec/busybox httpd -f -p 8081 -h /run/evidence &
while :; do
    dmesg > /run/evidence/dmesg.txt
    journalctl -b --no-pager -n 1600 > /run/evidence/journal.txt
    systemctl --failed --no-pager > /run/evidence/failed.txt
    loginctl --no-pager > /run/evidence/sessions.txt
    cat /proc/meminfo > /run/evidence/meminfo.txt
    ps -eo user,pid,comm,args > /run/evidence/processes.txt
    sleep 5
done
''',0o755)
add('etc/systemd/system/tb378fc-evidence.service','''[Unit]
Description=USB RAM desktop diagnostic evidence
After=systemd-journald.service
[Service]
ExecStart=/usr/local/libexec/tb378fc-evidence
KillMode=control-group
Restart=on-failure
[Install]
WantedBy=multi-user.target
''')
add('etc/systemd/system/tb378fc-usb-dhcp.service','''[Unit]
Description=Keep diagnostic USB DHCP leases valid after switch-root
After=local-fs.target
[Service]
ExecStart=/usr/local/libexec/busybox udhcpd -f /run/udhcpd.conf
Restart=on-failure
[Install]
WantedBy=multi-user.target
''')
add('etc/systemd/system/serial-getty@ttyGS0.service.d/ram.conf','''[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear --noissue --noclear -L ttyGS0 115200 vt100
''')
add('etc/systemd/system/tb378fc-ram-expiry.timer','''[Unit]
Description=End disposable desktop trial after 45 minutes in the desktop
[Timer]
OnActiveSec=45min
Unit=tb378fc-ram-expiry.service
[Install]
WantedBy=timers.target
''')
add('etc/systemd/system/tb378fc-ram-expiry.service','''[Unit]
Description=Return to Android after RAM trial
[Service]
Type=oneshot
ExecStart=/usr/local/libexec/busybox reboot -f
''')
add('usr/local/libexec/busybox',(ROOT/'inputs/busybox-root/usr/bin/busybox').read_bytes(),0o755)
# Retain firmware after the diagnostic initramfs is discarded.
add('usr/lib/firmware/novatek/tb378fc.bin',(ROOT/'diagnostics/firmware/novatek_ts_fw.bin').read_bytes())
for path in (ROOT/'diagnostics/firmware/gpu').glob('*'):
    if path.name not in ('gen80000_aqe.fw','gen80000_gmu.bin','gen80000_sqe.fw','gen80000_zap.mbn'):
        continue
    sub='qcom/sm8750/tb378fc/' if path.suffix=='.mbn' else 'qcom/'
    add('usr/lib/firmware/'+sub+path.name,path.read_bytes())
if args.wifi_firmware_dir:
    directory=args.wifi_firmware_dir.resolve()
    manifest=json.loads((directory/'manifest.json').read_text())
    assert manifest['hardware']=='WCN7860 hw2.0'
    for name,record in manifest['files'].items():
        assert name.startswith('ath12k/WCN7860/hw2.0/') and '..' not in name
        data=(directory/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==record['sha256']
        add('usr/lib/firmware/'+name,data)
    add('etc/NetworkManager/conf.d/90-tb378fc-usb.conf',
        '[keyfile]\nunmanaged-devices=interface-name:usb0\n')
    add('etc/NetworkManager/conf.d/91-tb378fc-wifi.conf',
        '[device]\nwifi.scan-rand-mac-address=no\n'
        '[connection]\nwifi.cloned-mac-address=preserve\n')
    add('usr/local/libexec/tb378fc-wifi-identity',
        (ROOT/'port/setup-wifi-identity.py').read_bytes(),0o755)
    add('etc/systemd/system/tb378fc-wifi-identity.service','''[Unit]
Description=Assign a local RAM WLAN address before starting NetworkManager
After=local-fs.target systemd-udev-trigger.service
Before=NetworkManager.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/libexec/tb378fc-wifi-identity
RemainAfterExit=yes
''')
    add('etc/systemd/system/NetworkManager.service.d/tb378fc-identity.conf','''[Unit]
Requires=tb378fc-wifi-identity.service
After=tb378fc-wifi-identity.service
''')
    add('usr/local/libexec/tb378fc-wifi-discovery',
        (ROOT/'port/wifi-passive-discovery.py').read_bytes(),0o755)
    add('etc/systemd/system/tb378fc-wifi-discovery.service','''[Unit]
Description=Supplement passive 5GHz discovery for the native WLAN firmware
After=NetworkManager.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/libexec/tb378fc-wifi-discovery
TimeoutStartSec=30
''')
    add('etc/systemd/system/tb378fc-wifi-discovery.timer','''[Unit]
Description=Check missing high-band discovery in the RAM trial
[Timer]
OnBootSec=30
OnUnitInactiveSec=15
AccuracySec=1
[Install]
WantedBy=timers.target
''')
if args.oriented_volume_keys:
    add('usr/local/libexec/tb378fc-volume-orientation',
        (ROOT/'port/volume-orientation.py').read_bytes(),0o755)
    add('etc/systemd/system/tb378fc-volume-orientation.service','''[Unit]
Description=Orient only the TB378FC native volume buttons with GNOME
After=display-manager.service
[Service]
ExecStart=/usr/bin/python3 /usr/local/libexec/tb378fc-volume-orientation
Restart=on-failure
RestartSec=5
[Install]
WantedBy=graphical.target
''')
links={
 'etc/systemd/system/default.target':'/usr/lib/systemd/system/graphical.target',
 'etc/systemd/system/multi-user.target.wants/tb378fc-evidence.service':'../tb378fc-evidence.service',
 'etc/systemd/system/multi-user.target.wants/tb378fc-usb-dhcp.service':'../tb378fc-usb-dhcp.service',
 'etc/systemd/system/getty.target.wants/serial-getty@ttyGS0.service':'/usr/lib/systemd/system/serial-getty@.service',
 'etc/systemd/system/timers.target.wants/tb378fc-ram-expiry.timer':'../tb378fc-ram-expiry.timer',
}
if args.reference_display_power:
    import importlib.util
    spec=importlib.util.spec_from_file_location('tb378fc_display_power',ROOT/'port/prepare-reference-display-power.py')
    display_power=importlib.util.module_from_spec(spec);spec.loader.exec_module(display_power)
    display_power.add_overlay(add,links)
if args.oriented_volume_keys:
    links['etc/systemd/system/graphical.target.wants/tb378fc-volume-orientation.service']='../tb378fc-volume-orientation.service'
if args.adsp_firmware_dir:
    directory=args.adsp_firmware_dir.resolve()
    manifest=json.loads((directory/'manifest.json').read_text())
    assert len(manifest['files'])==62
    for name,record in manifest['files'].items():
        assert Path(name).name==name and name.startswith(('adsp.','adsp_dtb.'))
        data=(directory/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==record['sha256'] and len(data)==record['size']
        add('usr/lib/firmware/qcom/sm8750/tb378fc/'+name,data)
if args.amp_firmware or args.audio_topology:
    assert args.amp_firmware and args.audio_topology
    import importlib.util
    spec=importlib.util.spec_from_file_location('tb378fc_audio',ROOT/'port/prepare-audio-desktop.py')
    audio=importlib.util.module_from_spec(spec);spec.loader.exec_module(audio)
    audio.add_audio_overlay(add,links,args.amp_firmware,args.audio_topology)
if args.hold_battery_ui:
    links['etc/systemd/system/upower.service']='/dev/null'
    links['etc/systemd/system/dbus-org.freedesktop.UPower.service']='/dev/null'
if args.zram:
    add('usr/local/libexec/tb378fc-zram',(ROOT/'port/setup-zram.sh').read_bytes(),0o755)
    add('etc/systemd/system/tb378fc-zram.service','''[Unit]
Description=Bounded RAM-only compressed swap for the disposable desktop
After=local-fs.target
Before=display-manager.service
[Service]
Type=oneshot
ExecStart=/bin/sh /usr/local/libexec/tb378fc-zram
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
''')
    links['etc/systemd/system/multi-user.target.wants/tb378fc-zram.service']='../tb378fc-zram.service'
if args.usb_ssh_runtime:
    record=json.loads(args.usb_ssh_runtime.with_suffix('.json').read_text())
    assert record['status']=='USB_ONLY_KEY_AUTH_VERIFIED_ON_DEVICE'
    allowed={'usr/sbin/sshd','usr/lib/openssh/sshd-session','usr/lib/openssh/sshd-auth',
             'usr/lib/openssh/sftp-server','etc/pam.d/sshd'}
    assert set(record['files'])==allowed
    with tarfile.open(args.usb_ssh_runtime) as payload:
        assert {m.name for m in payload}==allowed
        for m in payload:
            assert m.isfile()
            data=payload.extractfile(m).read()
            assert hashlib.sha256(data).hexdigest()==record['files'][m.name]
            add(m.name,data,m.mode & 0o777)
    key=args.usb_ssh_public_key.read_text().strip()
    assert key.startswith('ssh-ed25519 ') and '\n' not in key
    add('etc/tb378fc-usb-ssh.pub',key+'\n')
    add('usr/local/libexec/tb378fc-usb-ssh-setup',(ROOT/'port/setup-usb-ssh.sh').read_bytes(),0o755)
    add('etc/systemd/system/tb378fc-usb-ssh-setup.service','''[Unit]
Description=Ephemeral diagnostic SSH bound only to the USB interface
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/bin/sh /usr/local/libexec/tb378fc-usb-ssh-setup
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
''')
    links['etc/systemd/system/multi-user.target.wants/tb378fc-usb-ssh-setup.service']='../tb378fc-usb-ssh-setup.service'
    links['etc/systemd/system/ssh.service']='/dev/null'
    links['etc/systemd/system/ssh.socket']='/dev/null'
if args.validated_mesa_dir:
    checkpoint=args.validated_mesa_dir.resolve()
    proof=json.loads((checkpoint/'checkpoint.json').read_text())
    assert proof['status']=='HARDWARE_DRAW_AND_GNOME_DISPLAY_VERIFIED_RAM_ONLY'
    payload=checkpoint/'mesa-probe.tar'
    assert hashlib.sha256(payload.read_bytes()).hexdigest()==proof['files']['mesa-probe.tar']
    with tarfile.open(payload) as mesa:
        for member in mesa:
            name=member.name
            assert name.startswith(('usr/lib/erhai/mesa/','usr/local/libexec/')) or member.isdir()
            assert '..' not in Path(name).parts and not Path(name).is_absolute()
            if member.isfile():add(name,mesa.extractfile(member).read(),member.mode)
            elif member.issym():
                assert not Path(member.linkname).is_absolute() and '..' not in Path(member.linkname).parts
                links[name]=member.linkname
            else:assert member.isdir()
    add('etc/environment','')
    add('usr/lib/systemd/user-environment-generators/80-tb378fc-mesa',
        files['usr/local/libexec/tb378fc-mesa-user-env'][0],0o755)
# Keep desktop-trial services from configuring/mounting persistent tablet media.
for unit in ('NetworkManager.service','systemd-networkd.service','systemd-networkd.socket',
 'NetworkManager-wait-online.service','systemd-networkd-wait-online.service',
 'udisks2.service','fwupd.service','fwupd-refresh.service','snapd.service','snapd.socket',
 'cloud-init-local.service','cloud-init-network.service','cloud-init-main.service',
 'cloud-config.service','cloud-final.service','systemd-pstore.service',
 'plymouth-start.service','plymouth-quit.service','plymouth-quit-wait.service',
 'brltty.service','brltty-udev.service','brltty.path',
 'sleep.target','suspend.target','hibernate.target','hybrid-sleep.target'):
    links['etc/systemd/system/'+unit]='/dev/null'
if args.wifi_firmware_dir:
    links.pop('etc/systemd/system/NetworkManager.service')
    links['etc/systemd/system/multi-user.target.wants/NetworkManager.service']='/usr/lib/systemd/system/NetworkManager.service'
    links['etc/systemd/system/dbus-org.freedesktop.NetworkManager.service']='/usr/lib/systemd/system/NetworkManager.service'
    links['etc/systemd/system/timers.target.wants/tb378fc-wifi-discovery.timer']='../tb378fc-wifi-discovery.timer'
# The ISO optical-drive source is absent in this RAM root.
if (base/'etc/apt/sources.list.d/cdrom.sources').exists():
    source=(base/'etc/apt/sources.list.d/cdrom.sources').read_text()
    assert 'file:///cdrom' in source
    add('etc/apt/sources.list.d/cdrom.sources','Enabled: no\n'+source)
for unit in (base/'etc/systemd/system').glob('snap.*.service'):
    links['etc/systemd/system/'+unit.name]='/dev/null'
with tarfile.open(out/'settings.tar','w') as archive:
    dirs=set()
    for name in [*files,*links]:
        dirs.update(str(p) for p in Path(name).parents if str(p)!='.')
    for directory in sorted(dirs,key=lambda d:(d.count('/'),d)):
        info=tarfile.TarInfo(directory);info.type=tarfile.DIRTYPE;info.mode=0o755
        archive.addfile(info)
    for name,(data,mode) in sorted(files.items()):
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode
        info.mtime=mtimes.get(name,0)
        archive.addfile(info,io.BytesIO(data))
    for name,target in links.items():
        info=tarfile.TarInfo(name);info.type=tarfile.SYMTYPE;info.linkname=target;info.mode=0o777
        archive.addfile(info)
digest=hashlib.sha256((out/'settings.tar').read_bytes()).hexdigest()
template=(ROOT/'port/desktop-init').read_text()
assert template.count('@SETTINGS_SHA@')==1
(ROOT/'out/desktop-init').write_text(template.replace('@SETTINGS_SHA@',digest))
for name in ('minimal.squashfs','minimal.standard.squashfs'):
    path=out/name
    if not path.exists():path.symlink_to(ROOT/'inputs/ubuntu-desktop-layers/casper'/name)
(out/'settings-manifest.json').write_text(json.dumps({'sha256':digest,'files':sorted(files),'symlinks':links,'clock_epoch':args.clock_epoch,'rendering':'validated private Mesa; cold boot of this candidate still requires checking' if args.validated_mesa_dir else 'software trial'},indent=2)+'\n')
print(json.dumps({'settings_sha256':digest,'files':len(files)}))
