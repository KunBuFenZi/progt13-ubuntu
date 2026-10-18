#!/usr/bin/env python3
"""Download signed-repository packages into the SDK; no live device installation."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'upstream/tools/lib'))
import build_root
sdk=root/'out/sensor-stack67/root'
build_root.chroot(sdk,
    'mkdir -p /tb378fc-media68 && cd /tb378fc-media68 && apt-get download v4l-utils gstreamer1.0-plugins-bad',
    log=root/'logs/media-tools68-download.log')
print('MEDIA_TEST_PACKAGES_DOWNLOADED_ONLY',flush=True)
