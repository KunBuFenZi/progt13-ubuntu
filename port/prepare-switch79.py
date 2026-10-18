#!/usr/bin/env python3
"""Adapt the pinned OnePlus same-slot switcher to this Lenovo root container."""
import argparse
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='out/switch79')
args=parser.parse_args()
source=root/'reference/oneplus-coexist75/switch/erhai-switch'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='9919e85489935385dd9ce79a6dfed8e1b5c3b9c93de9faf752c602f5867625d9'
text=source.read_text(encoding='utf-8')
start=text.index('# erhai-switch --')
end=text.index('# Runs on both sides')
text=text[:start]+'''# tb378fc-switch -- same-slot Ubuntu / ColorOS triplet switcher for DEVICE_SERIAL_NOT_CONFIGURED.
# Derived from OnePlus Pad2Pro erhai-switch, commit adc57231281ac5bc8eb8ee012ffb04663e9f8226.
# Writes only boot/init_boot/vendor_boot in the active slot. Existing Android
# images are preseeded from the user's verified backups; no automatic backup.
# The dedicated ext4 root container holds its switch archive in /switch.
# The80GiB root container is installed; the switcher uses its shared archive.
#
'''+text[end:]
text=text.replace('PROG=erhai-switch','PROG=tb378fc-switch').replace('ROOT_LABEL=linux_rootfs','ROOT_LABEL=ubuntu')
text=text.replace('STORE_DEFAULT=/var/lib/erhai/switch','STORE_DEFAULT=/run/tb378fc-root/switch')
text=text.replace('MOUNTPOINT=/mnt/erhai-switch','MOUNTPOINT=/mnt/tb378fc-switch')
text=text.replace("UBUNTU_MARKER='erhai.boot=mainline'","UBUNTU_MARKER='tb378fc.stage=1'")
start=text.index('mount_store() {');end=text.index('\ncleanup() {',start)
text=text[:start]+'''mount_store() {
	[ -n "$STORE" ] && return 0
	if ! is_android; then
		[ -r /run/tb378fc-root/.tb378fc-root ] || die 'persistent root is not mounted'
		[ "$(cat /run/tb378fc-root/.tb378fc-root)" = tb378fc-root79 ] || die 'unexpected root container'
		STORE=$STORE_DEFAULT
		[ -d "$STORE" ] || die 'preseeded switch archive is missing'
		return 0
	fi
	ms_dev=$(resolve_part "$ROOT_LABEL") || die "no $ROOT_LABEL partition on this device"
	mkdir -p "$MOUNTPOINT" || die "cannot create $MOUNTPOINT"
	if ! grep -q " $MOUNTPOINT " /proc/mounts 2>/dev/null; then
		mount -t ext4 -o rw "$ms_dev" "$MOUNTPOINT" || die "cannot mount $ROOT_LABEL"
		MOUNTED_HERE=1
	fi
	[ "$(cat "$MOUNTPOINT/.tb378fc-root" 2>/dev/null)" = tb378fc-root79 ] || die 'unexpected root layout'
	STORE=$MOUNTPOINT/switch
	[ -d "$STORE" ] || die 'preseeded switch archive is missing'
}
'''+text[end:]
start=text.index('stash_set() {');end=text.index('\nwrite_meta() {',start)
text=text[:start]+'''stash_set() {
	die 'automatic boot backup disabled; import the existing verified Android triplet on the host'
}
'''+text[end:]
start=text.index('cmd_stash() {');end=text.index('\ncmd_to_ubuntu() {',start)
text=text[:start]+'''cmd_stash() {
	die 'reuse the existing verified Android triplet; no new boot backup is needed'
}
'''+text[end:]
text=text.replace('''	elif [ "$tu_who" != android ]; then
		if ! is_android && [ -d "$STORE/android" ]; then
			die 'unknown boot set; restore Android before switching'
		fi
		stash_set
	fi''','''	elif [ "$tu_who" != android ]; then
		die 'live boot set differs from the verified Android archive; refresh that archive offline first'
	fi''')
text=text.replace('''cmd_to_ubuntu() {
''','''cmd_to_ubuntu() {
	check_set "$STORE/android" android || die 'verified Android return set is required'
''')
marker='''if [ -n "$STORE" ]; then
	mkdir -p "$STORE"'''
gate='''# A ColorOS port may spoof ro.product.model; bind the real serial instead.
if [ -z "$DEV_DIR" ]; then
	serial=$(sed -n 's/.*androidboot.serialno=\\([^ ]*\\).*/\\1/p' /proc/cmdline 2>/dev/null)
	[ -n "$serial" ] || serial=$(getprop ro.serialno 2>/dev/null)
	# Lenovo ABL omits serial in mainline cmdline/bootconfig. The measured
	# Qualcomm SoC serial binds that Linux path to the same physical tablet.
	if [ "$serial" != DEVICE_SERIAL_NOT_CONFIGURED ]; then
		is_android && die 'this switch archive is for tablet DEVICE_SERIAL_NOT_CONFIGURED only'
		[ "$(cat /sys/devices/soc0/serial_number 2>/dev/null)" = SOC_SERIAL_NOT_CONFIGURED ] || die 'unexpected tablet SoC serial'
	fi
	[ "$SLOT" = _a ] || die 'only this tablet active A layout is prepared'
fi

'''
assert text.count(marker)==1;text=text.replace(marker,gate+marker)
text=text.replace('erhai-switch','tb378fc-switch').replace('OnePlus Pad 2 Pro.','Lenovo TB378FC.').replace('erhai marker','tb378fc marker')
text=text.replace('/var/lib/erhai/switch','/run/tb378fc-root/switch')
text=text.replace('stash-android   archive the live slot into <store>/android','stash-android   disabled: reuse existing verified Android images')
text=text.replace('to-ubuntu       archive Android, install the Ubuntu triplet, reboot','to-ubuntu       install the prepared Ubuntu triplet, reboot')
text=text.replace('to-ubuntu       archive Android, install <store>/ubuntu, reboot','to-ubuntu       install the prepared Ubuntu triplet, reboot')
out=root/args.output;out.mkdir(exist_ok=False)
(out/'tb378fc-switch').write_text(text,encoding='utf-8',newline='\n')
(out/'source.json').write_text(json.dumps({'upstream_commit':'adc57231281ac5bc8eb8ee012ffb04663e9f8226',
    'upstream_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(text.encode()).hexdigest(),
    'device':'TB378FC DEVICE_SERIAL_NOT_CONFIGURED','root_label':'ubuntu','store':'/switch in root container','auto_backup':False,
    'status':'PREPARED_NOT_DEVICE_INSTALLED'},indent=2)+'\n',encoding='utf-8')
print('Prepared Lenovo switcher, no live partition access')
