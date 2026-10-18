#!/usr/bin/env python3
"""Build additive microphone modules without replacing the live audio core/Image."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
kernel = root/'kernel'
base = root/'out/kernel-usbc70b'
work = root/'out/live-microphone71'
sdk = root/'out/module-microphone-sdk71'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume',action='store_true')
args = parser.parse_args()
if args.resume:
    assert work.is_dir() and sdk.is_dir() and (work/'base-sound.symvers').is_file()
else:
    work.mkdir(exist_ok=False)
    sdk.mkdir(exist_ok=False)
    shutil.copy2(base/'.config',sdk/'.config')
    shutil.copy2(kernel/'sound/Module.symvers',work/'base-sound.symvers')
    shutil.copy2(kernel/'drivers/soundwire/Module.symvers',work/'base-soundwire.symvers')
env = dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
requested = ['SND_SOC_WCD939X_SDW','SND_SOC_LPASS_VA_MACRO',
             'SND_SOC_LPASS_TX_MACRO','SND_SOC_LPASS_RX_MACRO','SOUNDWIRE_QCOM']
command = [str(kernel/'scripts/config'),'--file',str(sdk/'.config')]
for name in requested:
    command += ['-m',name]
subprocess.run(command,check=True)
def make(*args,extra=()):
    subprocess.run(['make','-C',str(kernel),'O='+str(sdk),'LOCALVERSION=+',
                    '-j4',*extra,*args],check=True,env=env)
make('olddefconfig','modules_prepare')
def config(path):
    return dict(re.findall(r'^(CONFIG_\w+)=(.*)$',path.read_text(),re.M))
old,new = config(base/'.config'),config(sdk/'.config')
delta = {key:{'before':old.get(key,'n'),'after':value} for key,value in new.items() if old.get(key)!=value}
assert not set(old)-set(new),set(old)-set(new)
assert all(value['before']=='n' and value['after']=='m' for value in delta.values()),delta
assert all(key.startswith('CONFIG_SND_SOC_') or key in ['CONFIG_SOUNDWIRE_QCOM','CONFIG_REGMAP_SOUNDWIRE']
           for key in delta),delta
for name in requested:
    assert new['CONFIG_'+name]=='m'
(work/'config-delta.json').write_text(json.dumps(delta,indent=2)+'\n')
(sdk/'Module.symvers').write_bytes((base/'vmlinux.symvers').read_bytes())
make('modules','M=drivers/slimbus')
slim = kernel/'drivers/slimbus/Module.symvers'
make('modules','M=drivers/soundwire',extra=['KBUILD_EXTRA_SYMBOLS='+str(work/'base-sound.symvers')+' '+str(slim)])
sdw = kernel/'drivers/soundwire/Module.symvers'
# Build just the newly required regmap transport, with its original headers.
regmap = work/'regmap'
regmap.mkdir(exist_ok=args.resume)
for path in (kernel/'drivers/base/regmap').glob('*.h'):
    shutil.copy2(path,regmap/path.name)
shutil.copy2(kernel/'drivers/base/regmap/regmap-sdw.c',regmap/'regmap-sdw.c')
(regmap/'Makefile').write_text('obj-m += regmap-sdw.o\n')
make('modules','M='+str(regmap),extra=['KBUILD_EXTRA_SYMBOLS='+str(sdw)])
symbols = ' '.join(str(path) for path in [work/'base-sound.symvers',sdw,regmap/'Module.symvers'])
make('modules','M=sound/soc/codecs',extra=['KBUILD_EXTRA_SYMBOLS='+symbols])
make('modules','M=drivers/pinctrl/qcom')
selected = ['snd-soc-wcd939x.ko','snd-soc-wcd939x-sdw.ko','snd-soc-wcd-mbhc.ko',
            'snd-soc-wcd-classh.ko','snd-soc-wcd-common.ko','snd-soc-lpass-macro-common.ko',
            'snd-soc-lpass-va-macro.ko','snd-soc-lpass-tx-macro.ko','snd-soc-lpass-rx-macro.ko',
            'soundwire-qcom.ko','slimbus.ko','regmap-sdw.ko','pinctrl-lpass-lpi.ko','pinctrl-sm8650-lpass-lpi.ko']
modules = work/'modules'
modules.mkdir(exist_ok=args.resume)
record = {'status':'BUILT_NOT_LOADED','base_kernel_image_sha256':hashlib.sha256((base/'arch/arm64/boot/Image').read_bytes()).hexdigest(),
          'config_delta':delta,'modules':{},'scope':'Additive modules only; existing sound/soundwire core, DSP services and Image untouched'}
bases = [kernel/'sound/soc/codecs',kernel/'drivers/soundwire',regmap,kernel/'drivers/pinctrl/qcom',kernel/'drivers/slimbus']
for name in selected:
    found = [folder/name for folder in bases if (folder/name).is_file()]
    assert len(found)==1,(name,found)
    target = modules/name
    shutil.copy2(found[0],target)
    vermagic = subprocess.check_output(['modinfo','-F','vermagic',str(target)],text=True).strip()
    assert vermagic=='7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64',vermagic
    imports = [line.split()[-1] for line in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(target)],text=True).splitlines()]
    exports = [line.split()[-1].removeprefix('__ksymtab_') for line in subprocess.check_output(['aarch64-linux-gnu-nm',str(target)],text=True).splitlines()
               if line.split() and line.split()[-1].startswith('__ksymtab_')]
    record['modules'][name] = {'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'vermagic':vermagic,'imports':imports,'exports':exports}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'status':record['status'],'modules':len(record['modules']),'config_delta':delta},indent=2))
