#!/usr/bin/env python3
"""Build a Lenovo v4 boot-layout trial from the working RAM environment.

Offline only: the root still comes from USB HTTP. This is not an installer.
The trial isolates the partition-format/AVB work from persistent-root changes.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='out/gki-trial78')
parser.add_argument('--ramdisk',type=Path)
parser.add_argument('--existing-key',type=Path)
parser.add_argument('--root-manifest',type=Path)
# Match the pinned OnePlus build-mainline-gki.py metadata. Omitting these
# fields made this Lenovo ABL mark the slot unbootable before Linux started.
parser.add_argument('--os-version',default='15.0.0')
parser.add_argument('--os-patch-level',default='2026-07')
args=parser.parse_args()
out = root/args.output; out.mkdir(exist_ok=False)
private = root/'out/private78'
if not args.existing_key:private.mkdir(mode=0o700,exist_ok=False)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
reference = root/'out/bootchain78'
stock = json.loads((reference/'existing-backups.json').read_text())
live = json.loads((reference/'live-backup-match.json').read_text())
for name in ['boot','init_boot','vendor_boot','vbmeta']:
    assert live[name]['sha256'] == stock['images'][name]['sha256']
mkboot = root/'inputs/mkbootimg/mkbootimg.py'
assert sha(mkboot)=='37d84b3d162e0bc62e36c1f4e1c63c85ea0caa9f29be023eb2f8efe006ad948c'
avb = reference/'avbtool.py'
assert sha(avb)=='14dc8d6ec533f551ec05ffd9a986ced0fd1290a201f62c91dad329dd51dfe3ed'
prior=json.loads((root/'out/boot-ufs77b/manifest.json').read_text())
image=root/'out/kernel-usbc70b/arch/arm64/boot/Image'
dtb=root/'out/recovery-tree75b/abl-static/erhai-abl.dtb'
ramdisk=args.ramdisk.resolve() if args.ramdisk else root/'out/initramfs-ufs77b/initramfs.cpio.gz'
assert sha(image)==prior['inputs']['kernel']['sha256']
assert sha(dtb)==prior['inputs']['dtb']['sha256']
if args.ramdisk:
    assert sha(ramdisk)==json.loads(ramdisk.with_name('manifest.json').read_text())['gzip_sha256']
else:
    assert sha(ramdisk)==prior['inputs']['ramdisk']['sha256']
cmdline=prior['cmdline']
name=b'TRAILER!!!\0'
header=b'070701'+b''.join(b'%08X'%v for v in (0,0,0,0,1,0,0,0,0,0,0,len(name),0))
empty=header+name; empty+=b'\0'*(-len(empty)%4)
(out/'empty.cpio.gz').write_bytes(gzip.compress(empty,mtime=0))
tool=[sys.executable,str(mkboot),'--header_version','4','--pagesize','4096',
      '--os_version',args.os_version,'--os_patch_level',args.os_patch_level]
subprocess.run(tool+['--kernel',str(image),'--cmdline',cmdline,'--output',str(out/'boot.img')],check=True)
subprocess.run(tool+['--ramdisk',str(out/'empty.cpio.gz'),'--output',str(out/'init_boot.img')],check=True)
subprocess.run(tool+['--vendor_ramdisk',str(ramdisk),'--dtb',str(dtb),'--vendor_cmdline','',
                     '--ramdisk_offset','0x01000000','--dtb_offset','0x01f00000','--tags_offset','0x100',
                     '--base','0','--kernel_offset','0x8000','--vendor_boot',str(out/'vendor_boot.img')],check=True)
key=args.existing_key.resolve() if args.existing_key else private/'tb378fc-trial-rsa4096.pem'
if not args.existing_key:
    subprocess.run(['openssl','genrsa','-out',str(key),'4096'],check=True)
    key.chmod(0o600)
parts={}
for name in ['boot','init_boot','vendor_boot']:
    p=out/(name+'.img'); b=p.read_bytes(); raw=len(b)
    if name=='vendor_boot':
        ver,page=struct.unpack_from('<II',b,8); vs=struct.unpack_from('<I',b,24)[0]
        ds=struct.unpack_from('<I',b,2100)[0]; align=lambda n:(n+4095)&~4095
        assert ver==4 and page==4096
        assert b[4096:4096+vs]==ramdisk.read_bytes()
        assert b[4096+align(vs):4096+align(vs)+ds]==dtb.read_bytes()
    else:
        ks,rs=struct.unpack_from('<II',b,8);assert struct.unpack_from('<I',b,40)[0]==4
        if name=='boot': assert rs==0 and b[4096:4096+ks]==image.read_bytes()
        else: assert ks==0 and gzip.decompress(b[4096:4096+rs])==empty
    text=(reference/(name+'-avb.txt')).read_text()
    rollback=int(re.search(r'^Rollback Index:\s+(\d+)',text,re.M).group(1))
    capacity=stock['images'][name]['bytes']
    salt=hashlib.sha256(b'tb378fc-trial78\0'+name.encode()+hashlib.sha256(b).digest()).hexdigest()
    subprocess.run([sys.executable,str(avb),'add_hash_footer','--image',str(p),'--partition_name',name,
                    '--partition_size',str(capacity),'--rollback_index',str(rollback),'--salt',salt,
                    '--algorithm','SHA256_RSA4096','--key',str(key)],check=True)
    info=subprocess.check_output([sys.executable,str(avb),'info_image','--image',str(p)],text=True)
    (out/(name+'-avb.txt')).write_text(info)
    assert p.stat().st_size==capacity
    assert int(re.search(r'Original image size:\s+(\d+)',info).group(1))==raw
    subprocess.run([sys.executable,str(avb),'verify_image','--image',str(p)],check=True)
    parts[name]={'file':p.name,'bytes':capacity,'raw_bytes':raw,'sha256':sha(p),'rollback_index':rollback,
                 'header_version':4,'self_avb_verified':True}
record={'status':'OFFLINE_SIGNED_TRIPLET_NOT_DEVICE_TESTED','scope':'Lenovo v4 partition-layout trial; still uses RAM root/USB HTTP',
        'not_an_installer':True,'not_flashed':True,'source_ram_build':'out/boot-ufs77b',
        'cmdline':cmdline,'partitions':parts,'source_backup_match':live,
        'os_version':args.os_version,'os_patch_level':args.os_patch_level,
        'reference_commit':'adc57231281ac5bc8eb8ee012ffb04663e9f8226',
        'key_sha256':sha(key),'known_remaining':['Bootloader acceptance of trial key and v4 triplet untested',
             'Writable UFS and persistent-root boot remain to be integrated','No data/partition install authorization']}
if args.root_manifest:
    record.update(scope='Lenovo v4 dedicated persistent root79; no HTTP downloads on this boot path',
                  root_filesystem=json.loads(args.root_manifest.read_text()),
                  known_remaining=['Device boot and bootloader acceptance of v4 triplet/new key',
                     'Root persistence across device reboot','Partition/data decision; not installed'])
(out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
(out/'SHA256SUMS').write_text(''.join(parts[n]['sha256']+'  '+n+'.img\n'
                                    for n in ['boot','init_boot','vendor_boot']))
print(json.dumps({'status':record['status'],'partitions':parts},indent=2))
