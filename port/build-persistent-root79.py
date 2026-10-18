#!/usr/bin/env python3
"""Build an offline sparse ext4 root container from the accepted77b desktop."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import uuid

root=Path(__file__).resolve().parent.parent
os.chdir(root)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume',action='store_true')
parser.add_argument('--finalize',action='store_true')
args=parser.parse_args()
out=root/'out/persistent-root79';out.mkdir(mode=0o700,exist_ok=args.resume or args.finalize)
def sha(p):
    digest=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def finish():
    staging=out/'staging'; image=out/'ubuntu-root79.ext4'
    meta=json.loads((staging/'rootfs.json').read_text())
    result=subprocess.run(['e2fsck','-f','-n',str(image)],capture_output=True,text=True)
    (out/'e2fsck.txt').write_text(result.stdout+result.stderr);result.check_returncode()
    for path in ['/.tb378fc-root','/upper/etc/tb378fc-root-layout','/rootfs.json']:
        r=subprocess.run(['debugfs','-R','cat '+path,str(image)],capture_output=True,text=True,check=True)
        assert 'tb378fc-root79' in r.stdout
    for name in meta['layers']:
        r=subprocess.check_output(['debugfs','-R','stat /layers/'+name,str(image)],stderr=subprocess.DEVNULL,text=True)
        assert 'Size: '+str((staging/'layers'/name).stat().st_size) in r
    changes=json.loads((out/'preparation.json').read_text()) if (out/'preparation.json').exists() else [
        {'removed':n} for n in ['etc/systemd/system/graphical.target.wants/tb378fc-ufs77.service',
        'etc/systemd/system/tb378fc-ufs77.service','usr/local/libexec/tb378fc-ufs77.py','usr/share/tb378fc/ufs77']]
    record={'status':'OFFLINE_ROOT_CONTAINER_BUILT_NOT_DEVICE_BOOTED','file':image.name,'bytes':image.stat().st_size,
        'allocated_bytes':image.stat().st_blocks*512,'sha256':sha(image),'uuid':meta['uuid'],'label':'tb378fc-ubuntu',
        'layout':'tb378fc-root79','root_mode':'persistent overlay with ext4 upper/work and two immutable squashfs layers',
        'settings_sha256':meta['settings_sha256'],'layers':meta['layers'],'changes_from_ram_settings':changes,
        'contains_private_user_settings':True,'host_fsck_passed':True,'tablet_storage_written':False,
        'known_remaining':['Early UFS/ext4 boot integration and device boot','Partition/data decision before installation']}
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    assert staging.resolve().is_relative_to(out.resolve())
    shutil.rmtree(staging)
    print(json.dumps(record,indent=2))

if args.finalize:
    assert not (out/'manifest.json').exists()
    finish()
    raise SystemExit(0)
assert not (out/'ubuntu-root79.ext4').exists() and not (out/'manifest.json').exists()
staging=out/'staging';staging.mkdir(exist_ok=args.resume)
upper=staging/'upper';upper.mkdir(exist_ok=args.resume)
for name in ['work','layers']:(staging/name).mkdir(exist_ok=args.resume)
settings=root/'out/private77b/settings-ufs77b.tar'
assert sha(settings)=='fea01315e4a9a68ba0f8d20ce46f059225b17cc5b117daa7a270f84bab670c88'
with tarfile.open(settings) as t:
    # This locally generated archive includes intentional /dev/null masks
    # and absolute systemd symlinks; retain their Unix semantics.
    for m in t:
        assert not m.name.startswith('/') and '..' not in Path(m.name).parts
        t.extract(m,upper)
home=upper/'home/pad'
if home.is_dir():
    os.chown(home,1000,1000)
    for directory,dirs,files in os.walk(home,followlinks=False):
        for name in dirs+files:os.lchown(Path(directory)/name,1000,1000)
changes=[]
for name in ['etc/systemd/system/graphical.target.wants/tb378fc-ufs77.service',
             'etc/systemd/system/tb378fc-ufs77.service','usr/local/libexec/tb378fc-ufs77.py']:
    p=upper/name
    if p.exists() or p.is_symlink():p.unlink();changes.append({'removed':name})
# UFS is initialized before root mount. Do not run the RAM read-only loader.
p=upper/'usr/share/tb378fc/ufs77'
if p.exists():shutil.rmtree(p);changes.append({'removed':'usr/share/tb378fc/ufs77'})
rule=upper/'etc/udev/rules.d/05-tb378fc-ufs77.rules'
rule.write_text('SUBSYSTEM=="block", KERNELS=="1d84000.ufs", ENV{UDISKS_IGNORE}="1"\n')
(upper/'etc/fstab').write_text('# Dedicated ext4 root container and persistent overlay are mounted by initramfs.\n')
(upper/'etc/tb378fc-root-layout').write_text('tb378fc-root79\n')
# Keep the accepted diagnostic access/settings during installation testing.
# Its one-shot setup uses a per-boot SSH key; no private host key is seeded.
layer_hashes={}
for name,expected in [('minimal.squashfs','82613d06f973778f6d49c817d7eb764a7fd812016a30a7f8006e8f61d718b393'),
                      ('minimal.standard.squashfs','fce0e2440cdbb6ebaf03efe3dd844c0e1a3b5facaca913e18f312e30a8f9fdaf')]:
    p=root/'inputs/ubuntu-desktop-layers/casper'/name;assert sha(p)==expected
    os.link(p,staging/'layers'/name);layer_hashes[name]=expected
root_uuid=str(uuid.uuid4())
proposal=json.loads((root/'out/ufs77/coexistence-proposal40g.json').read_text())
capacity=proposal['proposed_linux']['bytes']
(staging/'.tb378fc-root').write_text('tb378fc-root79\n')
(staging/'rootfs.json').write_text(json.dumps({'layout':'tb378fc-root79','uuid':root_uuid,
            'layers':layer_hashes,'settings_sha256':sha(settings),'persistent_upper':'upper','work':'work'},indent=2)+'\n')
image=out/'ubuntu-root79.ext4'
(out/'preparation.json').write_text(json.dumps(changes,indent=2)+'\n')
with image.open('xb') as f:f.truncate(capacity)
subprocess.run(['mke2fs','-q','-F','-t','ext4','-b','4096','-i','65536','-m','0','-J','size=64',
                '-U',root_uuid,'-L','tb378fc-ubuntu','-E','lazy_itable_init=0,lazy_journal_init=0',
                '-d',str(staging),str(image),str(capacity//4096)],check=True)
finish()
