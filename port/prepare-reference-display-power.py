#!/usr/bin/env python3
"""Adapt the reference project's backlight-only display policy to this board.

Source: yzddmr6/onepluspad-2pro-mainline, packaging/erhai-display-power.
Original GPL-2.0-only headers are retained in the copied files.
"""
from pathlib import Path


def add_overlay(add, links):
    root = Path(__file__).resolve().parent / 'display-power'
    for name in ('tb378fc-display-power.service', 'tb378fc-display-power.socket'):
        add('usr/lib/systemd/system/' + name, (root/name).read_bytes())
    add('usr/sbin/tb378fc-display-power', (root/'tb378fc-display-power').read_bytes(), 0o755)
    add('usr/lib/aarch64-linux-gnu/tb378fc/gsd-backlight-compat.so',
        (root/'gsd-backlight-compat.so').read_bytes(), 0o755)
    add('usr/lib/systemd/user/org.gnome.SettingsDaemon.Power.service.d/80-tb378fc-backlight.conf',
        (root/'80-tb378fc-backlight.conf').read_bytes())
    add('usr/lib/udev/rules.d/81-tb378fc-display-power.rules',
        (root/'81-tb378fc-display-power.rules').read_bytes())
    links['etc/systemd/system/sockets.target.wants/tb378fc-display-power.socket'] = \
        '/usr/lib/systemd/system/tb378fc-display-power.socket'
