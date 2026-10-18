#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
# Adapted from yzddmr6/onepluspad-2pro-mainline erhai-power-key,
# commit adc57231281ac5bc8eb8ee012ffb04663e9f8226.
# Lenovo adaptation: native Mutter backend and exact PMIC input discovery.
"""Route the tablet's physical power key to GNOME lock/blank and wake.

Only the selected input device is grabbed. Authentication remains with GNOME;
waking never calls ScreenSaver.SetActive(false), including in the greeter.

The display uses Mutter's PowerSaveMode on this board. The same physical
press wakes a blank display without deactivating GNOME's authentication.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import select
import struct
import subprocess
import time

EVENT = struct.Struct('llHHi')
KEY_POWER = 116
KEY_LEFTCTRL = 29
EVIOCGRAB = 0x40044590
STATUS = {'presses': 0}


def report(message):
    STATUS.update(last_action=message, boottime=time.clock_gettime(time.CLOCK_BOOTTIME))
    directory=Path('/run/tb378fc-power-key')
    directory.mkdir(mode=0o755,exist_ok=True)
    temporary=directory/'status.tmp'
    temporary.write_text(json.dumps(STATUS,indent=2)+chr(10))
    temporary.replace(directory/'status.json')
    print(message,flush=True)


# Written by the suspend cycle hook in its *pre* phase, i.e. before the tablet
# suspends and therefore before any press that is delivered on resume. Reading
# a post-phase marker instead was racy: userspace is thawed before that hook
# runs, so the service could see the resuming press first and suspend again.
#
# CLOCK_MONOTONIC keeps running across s2idle on this board, so clocks cannot
# detect the suspend either. Consumed once per handled press.
RESUME_FLAG = Path('/run/tb378fc-suspend-cycle')
RESUMED_STAMP = Path('/run/tb378fc-suspend-resumed')
RESUME_PRESS_WINDOW = 15


def suspended_since_last_press():
    if not RESUME_FLAG.exists():
        return False
    try:
        # The post hook stamps the resume. A flag whose resume is older than
        # the window was left by another wake source or a failed suspend.
        stale = time.time() - RESUMED_STAMP.stat().st_mtime > RESUME_PRESS_WINDOW
    except OSError:
        # No stamp yet: userspace thawed before the post hook ran, so this
        # is the press that resumed the tablet.
        stale = False
    for path in (RESUME_FLAG, RESUMED_STAMP):
        try:
            path.unlink()
        except OSError:
            pass
    return not stale


def command(argv, **kwargs):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=8, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'{argv[0]} failed')
    return result.stdout.strip()


def active_session():
    sid = command(['loginctl', 'show-seat', 'seat0', '-p', 'ActiveSession', '--value'])
    if not sid:
        raise RuntimeError('no active graphical session')
    text = command(['loginctl', 'show-session', sid, '-p', 'User', '-p', 'Class',
                    '-p', 'Type', '-p', 'Active', '-p', 'LockedHint'])
    info = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
    if info.get('Active') != 'yes' or info.get('Type') not in ('wayland', 'x11'):
        raise RuntimeError('active session is not a graphical desktop')
    if info.get('Class') not in ('user', 'user-early', 'greeter'):
        raise RuntimeError('unsupported graphical session class')
    return info


def call_session(info, dest, path, method, *args):
    uid = int(info['User'])
    account = pwd.getpwuid(uid)
    runtime = f'/run/user/{uid}'
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': account.pw_dir,
           'XDG_RUNTIME_DIR': runtime,
           'DBUS_SESSION_BUS_ADDRESS': f'unix:path={runtime}/bus'}
    return command(['gdbus', 'call', '--session', '--dest', dest, '--object-path',
                    path, '--method', method, *args], user=uid, group=account.pw_gid,
                   extra_groups=[], env=env)


def screensaver(info, method, *args):
    return call_session(info, 'org.gnome.ScreenSaver', '/org/gnome/ScreenSaver',
                        f'org.gnome.ScreenSaver.{method}', *args)


# Opt-in system suspend. Written by whoever enables it (an image default or the
# user); read at every press for the same reason as the display mode. When it is
# absent the service only locks and blanks, which is the shipped behaviour.
SUSPEND_MARKERS = (Path('/run/tb378fc/power-key-action'), Path('/etc/tb378fc/power-key-action'))


def suspend_requested():
    for marker in SUSPEND_MARKERS:
        try:
            if marker.read_text().strip() == 'suspend':
                return True
        except OSError:
            pass
    return False


def suspend():
    """Enter system suspend when opted in, and do nothing otherwise.

    The lock is already active at this point, so the resume path keeps the
    authentication boundary: waking restores the display only.
    """
    if not suspend_requested():
        return
    command(['systemctl', '--no-block', 'suspend'])
    report('power key: system suspend requested')


def mutter_mode(info, mode=None):
    """Mutter's PowerSaveMode: 0 on, 1-3 off; -1 (unknown) is refused below."""
    interface = 'org.gnome.Mutter.DisplayConfig'
    if mode is None:
        text = call_session(info, interface, '/org/gnome/Mutter/DisplayConfig',
                            'org.freedesktop.DBus.Properties.Get', interface,
                            'PowerSaveMode')
        match = re.fullmatch(r'\(<(?:int32 )?(-?\d+)>,\)', text)
        if not match:
            raise RuntimeError('Mutter did not report its power save mode')
        return int(match[1])
    call_session(info, interface, '/org/gnome/Mutter/DisplayConfig',
                 'org.freedesktop.DBus.Properties.Set', interface, 'PowerSaveMode',
                 f'<{mode}>')
    return mode


class WakeInput:
    def __init__(self):
        self.fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, 0x40045564, 1)  # UI_SET_EVBIT, EV_KEY
            fcntl.ioctl(self.fd, 0x40045565, KEY_LEFTCTRL)
            setup = struct.pack('HHHH80sI', 3, 0x1209, 4, 1, b'tb378fc-screen-wake', 0)
            fcntl.ioctl(self.fd, 0x405c5503, setup)  # UI_DEV_SETUP
            fcntl.ioctl(self.fd, 0x5501)  # UI_DEV_CREATE
        except Exception:
            os.close(self.fd)
            raise

    def wake(self):
        # A modifier press carries no text and does not unlock the session.
        # It clears the shell's black overlay and resets GNOME's idle state.
        for value in (1, 0):
            os.write(self.fd, EVENT.pack(0, 0, 1, KEY_LEFTCTRL, value))
            os.write(self.fd, EVENT.pack(0, 0, 0, 0, 0))
            if value:
                time.sleep(0.03)

    def close(self):
        os.close(self.fd)


def toggle(wake_input, resumed=False):
    info = active_session()
    display_mode = mutter_mode
    via = 'Mutter'
    if resumed:
        # The tablet just came back from suspend, and the resume path already
        # restored the display. This press only clears the shell's black
        # overlay; blanking or suspending here is what made a wake fall
        # straight back asleep, which is indistinguishable from not waking.
        display_mode(info, 0)
        wake_input.wake()
        report(f'power key: display on after resume via {via}; suspend suppressed')
        return
    mode = display_mode(info)
    if mode in (1, 2, 3):
        # Deactivating ScreenSaver slides GDM's login group offscreen too.
        # Real input clears only the black lightbox, preserving the dialog
        # and the authentication boundary in both greeter and user sessions.
        display_mode(info, 0)
        wake_input.wake()
        report(f'power key: display on via {via}; authentication unchanged')
        return
    if mode != 0:
        raise RuntimeError('display power state is unknown')

    if info['Class'] == 'greeter':
        # GDM already is the authentication boundary. Blanking the display
        # needs no ScreenSaver activation and must not enter its idle policy.
        display_mode(info, 3)
        report(f'power key: display off via {via} (greeter)')
        suspend()
        return
    # Lock waits for an active-state transition; a stale logind hint can
    # otherwise leave a repeated Lock call waiting on an already active shield.
    if screensaver(info, 'GetActive') != '(true,)':
        screensaver(info, 'Lock')

    deadline = time.monotonic() + 3
    while screensaver(info, 'GetActive') != '(true,)':
        if time.monotonic() >= deadline:
            raise RuntimeError('GNOME did not activate the lock/greeter screen')
        time.sleep(0.05)
    display_mode(info, 3)
    report(f'power key: display off via {via} ({info["Class"]})')
    suspend()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', type=Path, nargs='?', help='Power-key evdev node; defaults to this board pmic_pwrkey')
    args = parser.parse_args()
    if args.device is None:
        devices = [p for p in Path('/sys/class/input').glob('event*')
                   if (p/'device/name').read_text().strip() == 'pmic_pwrkey']
        if len(devices) != 1:
            parser.error('expected one pmic_pwrkey device')
        args.device = Path('/dev/input') / devices[0].name
    if not re.fullmatch(r'/dev/input/event\d+', str(args.device)):
        parser.error('expected /dev/input/eventN')
    fd = os.open(args.device, os.O_RDONLY | os.O_NONBLOCK)
    wake_input = None
    try:
        fcntl.ioctl(fd, EVIOCGRAB, 1)
        wake_input = WakeInput()
        report(f'power key: listening on {args.device}')
        pressed = False
        while True:
            select.select([fd], [], [])
            data = os.read(fd, EVENT.size * 16)
            if not data:
                return
            handled = False
            for _seconds, _usec, kind, code, value in EVENT.iter_unpack(data):
                if kind != 1 or code != KEY_POWER:
                    continue
                if value == 1:
                    pressed = True
                elif value == 0 and pressed:
                    pressed = False
                    if handled:
                        # A press made while suspended can deliver its press and
                        # release together with the wake; act once per read.
                        continue
                    handled = True
                    STATUS['presses'] += 1
                    # The suspend cycle flag is authoritative and is consumed
                    # here, once per handled press.
                    try:
                        toggle(wake_input, suspended_since_last_press())
                    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                        report(f'power key: {error}')
    finally:
        if wake_input is not None:
            wake_input.close()
        os.close(fd)  # Releases the exclusive grab, including on service stop.


if __name__ == '__main__':
    main()
