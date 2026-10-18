#!/usr/bin/env python3
"""Package native Wi-Fi, volume keys and the validated Mesa in a RAM desktop."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,default=ROOT/'out/boot-wireless-desktop-v2')
p.add_argument('--firmware-dir',type=Path,default=ROOT/'out/wifi-native-v2')
p.add_argument('--initramfs-output',type=Path,default=ROOT/'out/initramfs-wireless-desktop-v2')
p.add_argument('--kernel',type=Path,default=Path('out/kernel-wifi/arch/arm64/boot/Image'))
p.add_argument('--build-manifest',type=Path,default=Path('out/keys-build.json'))
p.add_argument('--zram',action='store_true')
p.add_argument('--usb-ssh-runtime',type=Path)
p.add_argument('--usb-ssh-public-key',type=Path)
p.add_argument('--image-name',default='boot-tb378fc-wireless-desktop-v2.img')
p.add_argument('--adsp-firmware-dir',type=Path)
p.add_argument('--amp-firmware',type=Path)
p.add_argument('--audio-topology',type=Path)
p.add_argument('--hold-battery-ui',action='store_true')
p.add_argument('--nr-cpus',type=int,choices=(7,8),default=7)
p.add_argument('--defer-secondary-cpus',action='store_true')
p.add_argument('--early-kms-test',type=Path,
               help='Diagnostic: initialize the panel before desktop startup')
p.add_argument('--early-kms-seconds',type=int,default=300)
p.add_argument('--early-kms-black',action='store_true')
p.add_argument('--online-after-early-kms',action='store_true')
p.add_argument('--reference-display-power',action='store_true')
p.add_argument('--dtb',type=Path,default=Path('out/abl-wifi-keys/erhai-abl.dtb'))
p.add_argument('--mainline-dtb',type=Path,default=Path('out/kernel-wifi/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-keys.dtb'))
args=p.parse_args()
assert 1 <= args.early_kms_seconds <= 300
assert not args.online_after_early_kms or (args.early_kms_test and args.defer_secondary_cpus)
assert not args.early_kms_black or args.early_kms_test
def run(*args):subprocess.run([str(a) for a in args],check=True)
assert not args.output.exists()
keys=json.loads(args.build_manifest.read_text())
for name,record in keys['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==record['sha256'],name
if not args.firmware_dir.exists():run(sys.executable,'port/prepare-native-wifi.py','--output',args.firmware_dir)
settings_extra=['--zram'] if args.zram else []
if args.reference_display_power:settings_extra+=['--reference-display-power']
firmware_extra=[]
if args.adsp_firmware_dir:
    settings_extra+=['--adsp-firmware-dir',args.adsp_firmware_dir]
    firmware_extra+=['--adsp-firmware-dir',args.adsp_firmware_dir]
if args.hold_battery_ui:settings_extra+=['--hold-battery-ui']
if args.amp_firmware or args.audio_topology:
    assert args.amp_firmware and args.audio_topology
    audio_extra=['--amp-firmware',args.amp_firmware,'--audio-topology',args.audio_topology]
    settings_extra+=audio_extra
    firmware_extra+=audio_extra
assert bool(args.usb_ssh_runtime)==bool(args.usb_ssh_public_key)
if args.usb_ssh_runtime:
    settings_extra+=['--usb-ssh-runtime',args.usb_ssh_runtime,'--usb-ssh-public-key',args.usb_ssh_public_key]
run(sys.executable,'port/prepare-desktop-settings.py',
    '--wifi-firmware-dir',args.firmware_dir,'--validated-mesa-dir','out/checkpoint-desktop-gpu-good',
    '--oriented-volume-keys',*settings_extra)
if args.reference_display_power:
    init=Path('out/desktop-init')
    text=init.read_text()
    anchor='echo TB378FC_DESKTOP_INIT_STARTED >/dev/kmsg\n'
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'''# Reference board compatibility policy: keep the MDSS parent runtime-active.
mdss=/sys/bus/platform/devices/ae00000.display-subsystem
if [ -e "$mdss/power/control" ]; then
    echo on >"$mdss/power/control"
    cat "$mdss/power/control" > /run/evidence/mdss-control.txt
    cat "$mdss/power/runtime_status" > /run/evidence/mdss-runtime.txt
else
    echo MDSS_PARENT_MISSING >/run/evidence/mdss-control.txt
fi
''')
    init.write_text(text)
if args.defer_secondary_cpus:
    init=Path('out/desktop-init')
    text=init.read_text()
    block='''for cpu in 1 2 3 4 5 6 7; do
    [ ! -f /sys/devices/system/cpu/cpu$cpu/online ] || echo 1 >/sys/devices/system/cpu/cpu$cpu/online
done'''
    assert text.count(block)==1
    init.write_text(text.replace(block,'# Secondary CPUs deferred for display-startup isolation.'))
if args.early_kms_test:
    init=Path('out/desktop-init')
    text=init.read_text()
    anchor='base=http://192.168.77.11:8088\n'
    assert text.count(anchor)==1
    text=text.replace(anchor,'''# Match the successful standalone probe before desktop/GPU userspace starts.
(
    sleep 12
    exec /bin/kms-test 300 cycle
) >/run/evidence/early-kms.txt 2>&1 &
early_kms_pid=$!
'''+anchor)
    text=text.replace('exec /bin/kms-test 300 cycle',
                      f'exec /bin/kms-test {args.early_kms_seconds} cycle')
    if args.early_kms_black:
        text=text.replace(f'/bin/kms-test {args.early_kms_seconds} cycle',
                          f'/bin/kms-test {args.early_kms_seconds} cycle black')
    if args.online_after_early_kms:
        line=f'exec /bin/kms-test {args.early_kms_seconds} cycle'+(' black' if args.early_kms_black else '')
        text=text.replace(line,line.removeprefix('exec ')+'''
    result=$?
    echo EARLY_KMS_RUN_EXIT=$result
    [ "$result" = 0 ] || exit "$result"
    if dmesg | grep -E 'TB_DSI_TIMEOUT|cmd dma tx failed|Unhandled context fault|I2C timeout'; then
        echo EARLY_KMS_KERNEL_FAULT
        exit 1
    fi
    for cpu in 1 2 3 4 5 6 7; do
        [ ! -f /sys/devices/system/cpu/cpu$cpu/online ] || echo 1 >/sys/devices/system/cpu/cpu$cpu/online || exit 1
    done
    echo EARLY_KMS_CPUS=$(cat /sys/devices/system/cpu/online)
''')
    switch='stage switch-root\n'
    assert text.count(switch)==1
    text=text.replace(switch,'''stage early-kms-handoff
kill -ALRM "$early_kms_pid" 2>/dev/null
wait "$early_kms_pid"
early_kms_result=$?
echo EARLY_KMS_EXIT=$early_kms_result >>/run/evidence/early-kms.txt
dmesg >/run/evidence/early-kms-dmesg.txt
[ "$early_kms_result" = 0 ] || fail early-kms
'''+switch)
    init.write_text(text)
run(sys.executable,'port/build-initramfs.py','--output',args.initramfs_output,
    '--init-script','out/desktop-init',
    *(['--kms-test',args.early_kms_test] if args.early_kms_test else []),
    '--extra-applets','wget sha256sum tar chown switch_root tee seq kill umount cp mv',
    '--touch-firmware','diagnostics/firmware/novatek_ts_fw.bin',
    '--gpu-firmware-dir','diagnostics/firmware/gpu','--wifi-firmware-dir',args.firmware_dir,
    *firmware_extra)
baseline=json.loads(Path('out/boot-desktop-awake/manifest.json').read_text())
base='rdinit=/init panic=15 mem_sleep_default=s2idle loglevel=7 log_buf_len=2M printk.time=1 tb378fc.stage=1'
assert baseline['cmdline'].startswith(base+' ')
extra_cmdline=baseline['cmdline'][len(base)+1:]
assert extra_cmdline.count('nr_cpus=7')==1
extra_cmdline=extra_cmdline.replace('nr_cpus=7',f'nr_cpus={args.nr_cpus}')
run(sys.executable,'port/package-stage1.py',
    '--kernel',args.kernel,
    '--dtb',args.dtb,
    '--mainline-dtb',args.mainline_dtb,
    '--ramdisk',args.initramfs_output/'initramfs.cpio.gz',
    '--build-manifest',args.build_manifest,'--extra-cmdline',extra_cmdline,
    '--output',args.output,'--image-name',args.image_name)
print('NATIVE_WIRELESS_KEYS_GPU_RAM_CANDIDATE_PACKAGED_NOT_YET_DEVICE_TESTED')
