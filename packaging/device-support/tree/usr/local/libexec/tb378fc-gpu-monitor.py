#!/usr/bin/python3
"""Small GPU monitor using the actual devfreq rate and cached engine sample."""
from collections import deque
import json
from pathlib import Path
import time
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib

SAMPLE=Path('/sys/kernel/tb378fc_gpu/sample')
FREQUENCY=Path('/sys/class/devfreq/3d00000.gpu/cur_freq')

def read_sample():
    raw={k:int(v) for k,v in (line.split('=',1) for line in SAMPLE.read_text().splitlines())}
    frequency=int(FREQUENCY.read_text())
    if raw['suspended'] or raw['polling_stopped']:
        usage=0.0
        state='Idle / power saving'
    elif raw['total']>0 and raw['busy']<=raw['total']:
        usage=100.0*raw['busy']/raw['total']
        state='Recent engine sample'
    else:
        usage=None
        state='Waiting for an engine sample'
    return {'frequency_hz':frequency,'usage_percent':usage,'state':state,'raw':raw}

class Monitor(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.tb378fc.GpuMonitor')
        self.connect('activate',self.activate)
        self.history=deque(maxlen=90)
        self.window=None
    def activate(self,app):
        if self.window:
            self.window.present();return
        self.window=Gtk.ApplicationWindow(application=app,title='Adreno GPU Monitor')
        self.window.set_default_size(540,360)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
        for side in ('top','bottom','start','end'):
            getattr(box,'set_margin_'+side)(20)
        self.window.set_child(box)
        name='Adreno 830v1'
        try:
            name=json.loads(Path('/run/evidence/power-sensors67/opengl-desktop.json').read_text())['renderer']
        except (OSError,KeyError,ValueError):
            pass
        title=Gtk.Label(label=name,xalign=0);title.add_css_class('title-1');box.append(title)
        api=Gtk.Label(label='OpenGL 4.6  ·  OpenGL ES 3.2  ·  Vulkan 1.4',xalign=0)
        api.add_css_class('dim-label');box.append(api)
        self.freq=Gtk.Label(xalign=0);self.freq.add_css_class('title-2');box.append(self.freq)
        self.load=Gtk.Label(xalign=0);box.append(self.load)
        self.bar=Gtk.ProgressBar();box.append(self.bar)
        self.history_label=Gtk.Label(label='',xalign=0)
        self.history_label.set_selectable(False);box.append(self.history_label)
        self.state=Gtk.Label(xalign=0);self.state.add_css_class('dim-label');box.append(self.state)
        note=Gtk.Label(label='Engine activity uses recent hardware samples, updated once per second.',xalign=0)
        note.set_wrap(True);note.add_css_class('dim-label');box.append(note)
        video=Gtk.Label(label='Video hardware decoding / encoding: not enabled yet',xalign=0)
        video.set_wrap(True);box.append(video)
        self.refresh();GLib.timeout_add_seconds(1,self.refresh)
        self.window.present()
    def refresh(self):
        try:
            sample=read_sample();usage=sample['usage_percent']
            self.freq.set_text(f"Clock   {sample['frequency_hz']/1e6:.0f} MHz")
            self.load.set_text('Engine activity   unavailable' if usage is None else f'Engine activity   {usage:.1f}%')
            self.bar.set_fraction(0 if usage is None else usage/100)
            self.state.set_text(sample['state'])
            self.history.append(usage)
        except (OSError,KeyError,ValueError) as error:
            self.load.set_text('GPU telemetry unavailable')
            self.state.set_text(str(error));self.history.append(None)
        glyphs='\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588'
        self.history_label.set_text(''.join(' ' if v is None else glyphs[min(7,int(v*7/100))] for v in list(self.history)[-45:]))
        return True

if __name__=='__main__':
    import sys
    if '--sample' in sys.argv:
        print(json.dumps(read_sample(),indent=2))
    else:
        Monitor().run(sys.argv)
