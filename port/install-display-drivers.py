#!/usr/bin/env python3
"""Install board display sources idempotently in the pinned kernel checkout."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
KERNEL = ROOT / 'kernel'
entries = [
    ('gpu/drm/panel', 'panel-novatek-nt36526', 'DRM_PANEL_TB378FC_NT36526', '''
config DRM_PANEL_TB378FC_NT36526
	tristate "Lenovo TB378FC CSOT NT36526 dual-DSI panel"
	depends on OF && DRM_MIPI_DSI && BACKLIGHT_CLASS_DEVICE
	help
	  Native 3504x2190 dual-DSI DSC panel on Lenovo TB378FC.
'''),
    ('video/backlight', 'tb378fc-aw99706b', 'BACKLIGHT_TB378FC_AW99706B', '''
config BACKLIGHT_TB378FC_AW99706B
	tristate "Lenovo TB378FC AW99706B backlight"
	depends on I2C && GPIOLIB && BACKLIGHT_CLASS_DEVICE
	select REGMAP_I2C
	help
	  AW99706B using the TB378FC vendor register configuration.
'''),
    ('regulator', 'tb378fc-panel-bias', 'REGULATOR_TB378FC_BIAS', '''
config REGULATOR_TB378FC_BIAS
	tristate "Lenovo TB378FC paired LCD bias"
	depends on I2C && GPIOLIB && OF
	select REGMAP_I2C
	help
	  Coupled ENP/ENN sequencing and native LCD bias register settings.
'''),
]
for directory, name, symbol, kconfig in entries:
    target = KERNEL / 'drivers' / directory
    shutil.copyfile(ROOT / 'port' / (name + '.c'), target / (name + '.c'))
    for file, marker, block in [
        ('Kconfig', '\nconfig ' + symbol + '\n', kconfig),
        ('Makefile', 'CONFIG_' + symbol, f'\nobj-$(CONFIG_{symbol}) += {name}.o\n'),
    ]:
        path = target / file
        text = path.read_text()
        if marker not in text:
            path.write_text(text + block)
print('DISPLAY_DRIVER_SOURCES_INSTALLED')
