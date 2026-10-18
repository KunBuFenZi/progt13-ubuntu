#!/usr/bin/env python3
"""Small unprivileged native torch window."""
import json
import socket
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib

def request(operation):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(2)
        connection.connect('/run/tb378fc-torch70.sock')
        connection.sendall(json.dumps({'op':operation}).encode()+b'\n')
        response = json.loads(connection.recv(1024))
    if 'error' in response:
        raise OSError(response['error'])
    return response

class Torch(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.lenovo.TB378FC.Torch')

    def do_activate(self):
        if self.get_active_window():
            self.get_active_window().present()
            return
        self.window = Gtk.ApplicationWindow(application=self,title='手电筒')
        self.window.set_default_size(360,200)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18)
        for side in ['top','bottom','start','end']:
            getattr(box,'set_margin_'+side)(24)
        self.status = Gtk.Label(label='已关闭')
        self.button = Gtk.Button(label='打开手电筒')
        self.button.connect('clicked',lambda button:self.refresh('toggle'))
        box.append(self.status)
        box.append(self.button)
        box.append(Gtk.Label(label='30 秒后自动关闭'))
        self.window.set_child(box)
        self.window.connect('close-request',self.close)
        self.refresh('state')
        self.timer = GLib.timeout_add(500,self.tick)
        self.window.present()

    def refresh(self,operation):
        try:
            state = request(operation)
            self.status.set_label(f"已打开 · {state['remaining']} 秒后关闭" if state['on'] else '已关闭')
            self.button.set_label('关闭手电筒' if state['on'] else '打开手电筒')
            self.button.set_sensitive(True)
        except (OSError,ValueError):
            self.status.set_label('手电筒暂不可用')
            self.button.set_sensitive(False)

    def tick(self):
        self.refresh('state')
        return True

    def close(self,window):
        GLib.source_remove(self.timer)
        try:
            request('off')
        except (OSError,ValueError):
            pass
        return False

Torch().run()
