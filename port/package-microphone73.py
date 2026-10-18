#!/usr/bin/env python3
"""Build a complete static-DT RAM trial from accepted70f; never flash or select it."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile

root=Path(__file__).resolve().parent.parent
os.chdir(root)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume',action='store_true')
args=parser.parse_args()
work=root/'out/runtime-microphone73'
work.mkdir(exist_ok=args.resume)
assert not (root/'out/boot-microphone73/boot-tb378fc-microphone73.img').exists()
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
modules=root/'out/microphone73'
module_manifest=json.loads((modules/'manifest.json').read_text())
assert module_manifest['status']=='NATIVE_ADC_MAP73_BUILT_NOT_LOADED'
base=root/'out/private70/settings-accepted-usbc70f.tar'
accepted=json.loads((root/'out/runtime-usbc70f/host-verified.json').read_text())
assert sha(base)==accepted['settings_sha256']
entries={}
with tarfile.open(base) as archive:
    for item in archive:
        assert not item.name.startswith('/') and '..' not in Path(item.name).parts
        entries[item.name]=(copy.copy(item),archive.extractfile(item).read() if item.isfile() else None)
def add(name,data,mode=0o644):
    item=tarfile.TarInfo(name);item.mode=mode;item.size=len(data)
    entries[name]=(item,data)
prefix='usr/share/tb378fc/microphone73/'
for name,entry in module_manifest['modules'].items():
    source=modules/'modules'/name;assert sha(source)==entry['sha256']
    add(prefix+'modules/'+name,source.read_bytes())
add(prefix+'manifest.json',(modules/'manifest.json').read_bytes())
# Candidate only: desktop UCM remains speaker-only, avoiding capture probing.
add(prefix+'Mic73.conf',(root/'port/audio/Mic73.conf').read_bytes())
add('usr/local/libexec/tb378fc-microphone73.py',(root/'port/tb378fc-microphone73.py').read_bytes(),0o755)
add('etc/systemd/system/tb378fc-microphone73.service',(root/'port/tb378fc-microphone73.service').read_bytes())
link='etc/systemd/system/graphical.target.wants/tb378fc-microphone73.service'
item=tarfile.TarInfo(link);item.type=tarfile.SYMTYPE;item.mode=0o777;item.linkname='../tb378fc-microphone73.service'
entries[link]=(item,None)
capture=root/'out/microphone-capture71'
capture_manifest=json.loads((capture/'manifest.json').read_text())
topology=capture/'Lenovo-TB378FC-tplg.bin'
assert sha(topology)==capture_manifest['files'][topology.name]
add('usr/lib/firmware/qcom/sm8750/Lenovo-TB378FC-tplg.bin',topology.read_bytes())
assert not any('live-microphone' in name or 'recover-speaker' in name for name in entries)
private=root/'out/private73';private.mkdir(exist_ok=True);private.chmod(0o700)
target=private/'settings-microphone73.tar'
if target.exists():
    assert args.resume
    with tarfile.open(target) as archive:
        assert set(archive.getnames())==set(entries)
        for observed in archive:
            expected,data=entries[observed.name]
            assert (observed.type,observed.mode,observed.linkname,observed.uid,observed.gid)==(expected.type,expected.mode,expected.linkname,expected.uid,expected.gid)
            if observed.isfile():assert archive.extractfile(observed).read()==data
else:
    with target.open('xb') as handle:
        target.chmod(0o600)
        with tarfile.open(fileobj=handle,mode='w') as archive:
            for name,(item,data) in sorted(entries.items()):archive.addfile(item,io.BytesIO(data) if data is not None else None)
tree=root/'out/microphone-tree73';tree.mkdir(exist_ok=args.resume)
dtb=tree/'sm8750-lenovo-tb378fc-microphone73.dtb'
source=capture/'offline-merged.dtb'
assert sha(source)==capture_manifest['files'][source.name]
shutil.copy2(source,dtb)
# All references are flattened now. ABL's compatibility wrapper supplies its
# own stock symbols and requires the input to have no overlay-only symbols.
subprocess.run(['fdtput','-r',str(dtb),'/__symbols__'],check=True)
# fdtget verifies the final flattened references, including the previously
# phandle-less existing TX controller. No live overlay is involved at boot.
get=lambda path,prop:subprocess.check_output(['fdtget','-t','x',str(dtb),path,prop],text=True).split()
subprocess.run(['fdtput','-t','i',str(dtb),'/soc@0/soundwire@7630000/codec@0,3','qcom,tx-port-mapping','3','4','3','4'],check=True)
bus=get('/soc@0/soundwire@7630000','phandle')[0]
assert get('/sound/wcd-capture-dai-link/codec','sound-dai')[2]==bus
assert get('/tb378fc-wcd939x','vdd-px-supply')==['bd']
subprocess.run([sys.executable,'reference-tools/build-erhai-abl-symbols.py','--mainline-dtb',str(dtb),
                '--dtbo-img','inputs/dtbo.img','--base-dir','inputs/stock-base','--identity-index','11',
                '--dtc','out/kernel-usbc70b/scripts/dtc/dtc','--output',str(tree/'abl-static')],check=True)
script=(root/'port/desktop-init').read_text();assert script.count('@SETTINGS_SHA@')==1
(work/'init').write_text(script.replace('@SETTINGS_SHA@',sha(target)))
subprocess.run([sys.executable,'port/build-initramfs.py','--output','out/initramfs-microphone73',
                '--init-script',str(work/'init'),'--extra-applets','wget sha256sum tar chown switch_root tee seq kill umount cp mv',
                '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin','--gpu-firmware-dir','diagnostics/firmware/gpu',
                '--wifi-firmware-dir','out/wifi-native-v2','--adsp-firmware-dir','diagnostics/firmware/adsp'],check=True)
build=json.loads((root/'out/runtime-usbc70f/build-manifest.json').read_text())
build.update(status='STATIC_MICROPHONE73_CANDIDATE_NOT_BOOTED',settings_sha256=sha(target))
build['files'][dtb.relative_to(root).as_posix()]={'sha256':sha(dtb),'size':dtb.stat().st_size}
(work/'build-manifest.json').write_text(json.dumps(build,indent=2)+'\n')
cmd=json.loads((root/'out/boot-usbc70f/manifest.json').read_text())['cmdline']
prefix='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1 '
assert cmd.startswith(prefix)
subprocess.run([sys.executable,'port/package-stage1.py','--kernel','out/kernel-usbc70b/arch/arm64/boot/Image',
                '--dtb',str(tree/'abl-static/erhai-abl.dtb'),'--mainline-dtb',str(dtb),
                '--ramdisk','out/initramfs-microphone73/initramfs.cpio.gz','--build-manifest',str(work/'build-manifest.json'),
                '--extra-cmdline',cmd[len(prefix):],'--output','out/boot-microphone73',
                '--image-name','boot-tb378fc-microphone73.img'],check=True)
record={'status':'STATIC_MICROPHONE73_CANDIDATE_READY_NOT_SELECTED_OR_BOOTED',
        'settings_sha256':sha(target),'base_settings_sha256':sha(base),
        'boot_sha256':sha(root/'out/boot-microphone73/boot-tb378fc-microphone73.img'),
        'dtb_sha256':sha(dtb),'kernel_unchanged_from_accepted70':True,
        'build_id':(root/'out/initramfs-microphone73/build-id').read_text().strip(),
        'codec_irq_lifetime_patch_sha256':module_manifest['patch_sha256'],
        'speaker_topology_prefix_unchanged':True,'no_capture_stream_opened':True,
        'no_hot_controller_replacement_or_codec_unload':True,
        'remaining':['Native map73 cold-boot regression','Mic PCM hardware verification; capture remains unopened']}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
