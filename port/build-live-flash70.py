#!/usr/bin/env python3
"""Build the live flash drivers against the exact USB70b kernel, without an Image."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', default='out/live-flash70')
args = parser.parse_args()
work = (root/args.output).resolve()
assert work.is_relative_to(root/'out')
work.mkdir(exist_ok=False)
sdk = root/'out/kernel-usbc70b'
kernel = root/'kernel'
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert 'CONFIG_OF_OVERLAY=y' in (sdk/'.config').read_text()
original = json.loads((root/'out/native-flash70/manifest.json').read_text())
overlay = root/'out/native-flash70/tb378fc-flash70.dtbo'
assert sha(overlay) == original['overlay_sha256']
shutil.copy2(overlay, work/overlay.name)
for name, source in [('led-class-flash', kernel/'drivers/leds/led-class-flash.c'),
                     ('leds-qcom-flash', kernel/'drivers/leds/flash/leds-qcom-flash.c'),
                     ('live-flash-overlay70', root/'port/live-flash-overlay70.c')]:
    shutil.copy2(source, work/(name+'.c'))
(work/'Makefile').write_text('obj-m += led-class-flash.o leds-qcom-flash.o live-flash-overlay70.o\n')
(sdk/'Module.symvers').write_bytes((sdk/'vmlinux.symvers').read_bytes())
subprocess.run(['make','-C',str(kernel),'O='+str(sdk),'LOCALVERSION=+',
                '-j2','M='+str(work),'modules'],check=True,
               env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-'))
exports = {line.split()[1] for table in [sdk/'vmlinux.symvers', work/'Module.symvers']
           for line in table.read_text().splitlines()}
modules = {}
for module in work.glob('*.ko'):
    imports = {line.split()[-1] for line in subprocess.check_output(
        ['aarch64-linux-gnu-nm','-u',str(module)],text=True).splitlines()}
    assert not imports-exports, imports-exports
    vermagic = subprocess.check_output(['modinfo','-F','vermagic',str(module)],text=True).strip()
    assert vermagic == '7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64', vermagic
    modules[module.name] = {'sha256':sha(module),'bytes':module.stat().st_size,'vermagic':vermagic}
record = {'status':'BUILT_NOT_LOADED','kernel':'out/kernel-usbc70b',
          'kernel_image_sha256':sha(sdk/'arch/arm64/boot/Image'),
          'config_sha256':sha(sdk/'.config'),'modules':modules,
          'overlay_sha256':sha(work/overlay.name),
          'default':'off','torch_total_uA':100000,'flash_total_uA':200000,
          'timeout_us':200000,'native_id':original['native_flash_id']}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
