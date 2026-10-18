#!/usr/bin/env python3
"""Add persistent-root shutdown support and package the80GiB install boot set."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
root=Path(__file__).resolve().parent.parent;os.chdir(root)
early=root/'out/early-root79';m=json.loads((early/'manifest.json').read_text())
p=early/'bin/persistent-shutdown80';p.write_bytes((root/'port/persistent-shutdown80').read_bytes())
m['files']['bin/persistent-shutdown80']={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mode':0o755}
(early/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
subprocess.run([sys.executable,'port/build-initramfs.py','--output','out/initramfs-persistent80',
    '--init-script','port/persistent-init79','--runtime-dir',str(early),
    '--extra-applets','wget sha256sum tar chown switch_root tee seq kill umount cp mv insmod findfs chmod losetup poweroff halt',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin','--gpu-firmware-dir','diagnostics/firmware/gpu',
    '--wifi-firmware-dir','out/wifi-native-v2','--adsp-firmware-dir','diagnostics/firmware/adsp'],check=True)
subprocess.run([sys.executable,'port/package-gki78.py','--output','out/gki-persistent80',
    '--ramdisk','out/initramfs-persistent80/initramfs.cpio.gz',
    '--existing-key','out/private78/tb378fc-trial-rsa4096.pem',
    '--root-manifest','out/persistent-root79/manifest.json'],check=True)
