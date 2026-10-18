#!/usr/bin/env python3
"""Build isolated SCSI/UFS modules with media-write rejection for a RAM trial."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
os.chdir(root)
kernel = root / 'kernel'
base = root / 'out/kernel-usbc70b'
sdk = root / 'out/kernel-ufs77'
sources = root / 'out/ufs77-source'
out = root / 'out/ufs77-modules'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume', action='store_true')
args = parser.parse_args()
if args.resume:
    assert sdk.is_dir() and sources.is_dir() and out.is_dir()
    assert not (out / 'manifest.json').exists()
else:
    assert not sdk.exists() and not sources.exists() and not out.exists()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins = {'drivers/scsi/sd.c': '8524170932128913c9e34e74f42643ec0b9273a1dfe24990357948de0f45c8eb',
        'drivers/ufs/core/ufshcd.c': '2f610a861ecd220dc6a3bc7744c031adcb71b77c3a8d66e7d4d43bcbcc6c7e47'}
assert all(len(value) == 64 for value in pins.values())
for name, digest in pins.items():
    assert sha(kernel / name) == digest, name
assert sha(base / 'arch/arm64/boot/Image') == '21c91b2dddf71e38ed6ae4366135a56ec9e02fe9d617bba33937b3e40c6483e9'
base_config = (base / '.config').read_bytes()
base_exports = (base / 'vmlinux.symvers').read_bytes()
def prepare_sources():
    subprocess.run(['cp', '-a', '--reflink=auto', str(base), str(sdk)], check=True)
    sources.mkdir(); out.mkdir()
    for name in ['scsi', 'ufs']:
        shutil.copytree(kernel / 'drivers' / name, sources / name)

    disk = sources / 'scsi/sd.c'
    text = disk.read_text()
    start = text.index('static void\nsd_read_write_protect_flag(')
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    text = text[:brace] + '''{
    	/* RAM inspection driver: never present an internal LUN as writable. */
    	sdkp->write_prot = 1;
    	set_disk_ro(sdkp->disk, 1);
    	sd_first_printk(KERN_NOTICE, sdkp, "TB378FC_UFS77 forced read-only\\n");
    }''' + text[end:]
    needle = '\terror = device_add_disk(dev, gd, NULL);'
    assert text.count(needle) == 1
    text = text.replace(needle, '\tsdkp->write_prot = 1;\n\tset_disk_ro(gd, 1);\n' + needle)
    disk.write_text(text)

    core = sources / 'ufs/core/ufshcd.c'
    text = core.read_text()
    needle = 'static enum scsi_qc_status ufshcd_queuecommand(struct Scsi_Host *host,'
    assert text.count(needle) == 1
    guard = '''/* Board bring-up only: allow media reads and discovery/power controls.
     * Protocol link initialization still uses the normal UFS control path. */
    static bool tb378fc_ufs77_read_command(const struct scsi_cmnd *cmd)
    {
    	if (cmd->sc_data_direction == DMA_TO_DEVICE ||
    	    cmd->sc_data_direction == DMA_BIDIRECTIONAL)
    		return false;
    	switch (cmd->cmnd[0]) {
    	case TEST_UNIT_READY:
    	case REQUEST_SENSE:
    	case INQUIRY:
    	case MODE_SENSE:
    	case MODE_SENSE_10:
    	case READ_CAPACITY:
    	case SERVICE_ACTION_IN_16:
    	case REPORT_LUNS:
    	case LOG_SENSE:
    	case READ_6:
    	case READ_10:
    	case READ_12:
    	case READ_16:
    	case START_STOP:
    		return true;
    	default:
    		return false;
    	}
    }

    '''
    text = text.replace(needle, guard + needle)
    needle = '\tstruct ufs_hw_queue *hwq = NULL;\n\n\tswitch (hba->ufshcd_state) {'
    assert text.count(needle) == 1
    text = text.replace(needle, '''\tstruct ufs_hw_queue *hwq = NULL;

    	if (!tb378fc_ufs77_read_command(cmd)) {
    		pr_warn_ratelimited("TB378FC_UFS77 blocked opcode %#x direction %d\\n",
    				    cmd->cmnd[0], cmd->sc_data_direction);
    		scsi_build_sense(cmd, 0, DATA_PROTECT, 0x27, 0);
    		scsi_done(cmd);
    		return 0;
    	}

    	switch (hba->ufshcd_state) {''')
    core.write_text(text)


if not args.resume:
    prepare_sources()
disk = sources / 'scsi/sd.c'
core = sources / 'ufs/core/ufshcd.c'
assert 'TB378FC_UFS77 forced read-only' in disk.read_text()
assert 'tb378fc_ufs77_read_command' in core.read_text()
# External Kbuild needs an absolute prerequisite for this generated header.
makefile = sources / 'scsi/Makefile'
text = makefile.read_text()
old_prerequisite = 'include/scsi/scsi_devinfo.h FORCE'
new_prerequisite = '$(srctree)/include/scsi/scsi_devinfo.h FORCE'
if new_prerequisite not in text:
    assert text.count(old_prerequisite) == 1
    makefile.write_text(text.replace(old_prerequisite, new_prerequisite))

env = dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-')
cfg = [str(kernel / 'scripts/config'), '--file', str(sdk / '.config')]
for name in ['SCSI', 'BLK_DEV_SD', 'SCSI_UFSHCD', 'SCSI_UFSHCD_PLATFORM', 'SCSI_UFS_QCOM']:
    subprocess.run(cfg + ['--module', name], check=True)
for name in ['SCSI_UFS_BSG', 'SCSI_UFS_CRYPTO', 'SCSI_UFS_HWMON', 'RPMB', 'CHR_DEV_SG', 'CHR_DEV_ST', 'BLK_DEV_SR']:
    subprocess.run(cfg + ['--disable', name], check=True)
make = ['make', '-C', str(kernel), 'O=' + str(sdk), 'LOCALVERSION=+', '-j2']
subprocess.run(make + ['olddefconfig'], env=env, check=True)
subprocess.run(make + ['modules_prepare'], env=env, check=True)
(sdk / 'Module.symvers').write_bytes(base_exports)
symvers = []
for directory in [sources / 'scsi', sources / 'ufs/core', sources / 'ufs/host']:
    command = make + ['M=' + str(directory), 'modules']
    if symvers:
        command += ['KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, symvers))]
    subprocess.run(command, env=env, check=True)
    symvers.append(directory / 'Module.symvers')

modules = {}
wanted = {'scsi_mod.ko', 'scsi_common.ko', 'sd_mod.ko', 'ufshcd-core.ko', 'ufshcd-pltfrm.ko', 'ufs-qcom.ko'}
for path in sources.rglob('*.ko'):
    if path.name not in wanted:
        continue
    assert path.name not in modules
    imports = [line.split()[-1] for line in subprocess.check_output(['aarch64-linux-gnu-nm', '-u', str(path)], text=True).splitlines()]
    exports = [line.split()[-1].removeprefix('__ksymtab_') for line in
               subprocess.check_output(['aarch64-linux-gnu-nm', str(path)], text=True).splitlines()
               if line.split() and line.split()[-1].startswith('__ksymtab_')]
    vermagic = subprocess.check_output(['modinfo', '-F', 'vermagic', str(path)], text=True).strip()
    assert vermagic == '7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
    modules[path.name] = {'sha256': sha(path), 'imports': imports, 'exports': exports, 'vermagic': vermagic}
    shutil.copy2(path, out / path.name)
assert set(modules) == wanted, set(modules)
available = {line.split()[1] for line in base_exports.decode().splitlines()}
pending = dict(modules); order = []
while pending:
    ready = sorted(name for name, item in pending.items() if not set(item['imports']) - available)
    assert ready, {name: sorted(set(item['imports']) - available) for name, item in pending.items()}
    for name in ready:
        order.append(name); available.update(pending.pop(name)['exports'])
assert (base / '.config').read_bytes() == base_config and (base / 'vmlinux.symvers').read_bytes() == base_exports
assert all(sha(kernel / name) == value for name, value in pins.items())
old = dict(line.split('=', 1) for line in base_config.decode().splitlines() if '=' in line)
new = dict(line.split('=', 1) for line in (sdk / '.config').read_text().splitlines() if '=' in line)
record = {'status': 'READ_ONLY_MODULES_BUILT_NOT_LOADED', 'modules': modules, 'order': order,
          'source_pins': pins, 'patched_sources': {'sd.c': sha(disk), 'ufshcd.c': sha(core), 'scsi/Makefile': sha(makefile)},
          'config_values_changed': {key: [old.get(key), new.get(key)] for key in old.keys() | new.keys() if old.get(key) != new.get(key)},
          'baseline_image_config_and_exports_preserved': True,
          'read_only_guards': ['sd forced read-only before disk registration and revalidation',
                               'UFS queue rejects data-out and non-read/non-discovery opcodes with DATA_PROTECT'],
          'scope': 'RAM-only discovery modules; no internal media writes, no RPMB/BSG endpoints'}
(out / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: v for k, v in record.items() if k != 'modules'}, indent=2))
