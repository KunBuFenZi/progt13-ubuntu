#!/usr/bin/env python3
"""Prepare and compile read-only Lenovo PPS diagnostics in the existing battmgr.

No new GLINK client, charger writes, Image build, loading, or reboot.
"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='out/native-pps71')
args = parser.parse_args()
work = (root/args.output).resolve()
assert work.is_relative_to(root/'out')
work.mkdir(exist_ok=False)
source = root/'out/native-usb-power70/qcom_battmgr.c'
base_manifest = json.loads((source.parent/'manifest.json').read_text())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert sha(source) == base_manifest['candidate_source_sha256']
native = root/'reference/native-peripherals70/qti_battery_charger.c'
enum = re.search(r'enum huaqin_property_id\s*\{(.*?)\};',native.read_text(),re.S).group(1)
assert '=' not in enum
identifiers = re.findall(r'\bHQ_POWER_SUPPLY_PROP_[A-Z0-9_]+\b',enum)
assert len(identifiers) == len(set(identifiers))
fields = {
    'pps_status':'PPS_STATUS',
    'ibus_total_raw':'IBUS_TOTAL',
    'sc8541_master_ibus_raw':'SC8541_MATSET_IBUS',
    'sc8541_slave_ibus_raw':'SC8541_SLAVE_IBUS',
    'fg1_current_raw':'FG_1_CURRENT',
    'fg2_current_raw':'FG_2_CURRENT',
    'fg1_voltage_raw':'FG_1_VOLTAGE',
    'fg2_voltage_raw':'FG_2_VOLTAGE',
    'fg1_temperature_raw':'FG_1_TEMP',
    'fg2_temperature_raw':'FG_2_TEMP',
}
properties = {name:identifiers.index('HQ_POWER_SUPPLY_PROP_'+symbol) for name,symbol in fields.items()}
text = source.read_text()
def replace(old,new):
    global text
    assert text.count(old)==1,old[:100]
    text = text.replace(old,new)

replace('#define BATTMGR_BAT_PROPERTY_GET\t0x30',
        '#define BATTMGR_NATIVE_LENOVO_PROPERTY_GET 0x60\n#define BATTMGR_BAT_PROPERTY_GET\t0x30')
replace('\tbool service_up;','''\tbool service_up;

	/* Read-only Lenovo diagnostics use the existing serialized GLINK client. */
	bool lenovo_read_pending;
	u32 lenovo_property;
	u32 lenovo_value;''')
anchor = '\tswitch (opcode) {\n\tcase BATTMGR_BAT_PROPERTY_GET:'
replace(anchor,'''\tswitch (opcode) {
	case BATTMGR_NATIVE_LENOVO_PROPERTY_GET:
		/* A late OEM response must never ACK an unrelated battery request. */
		if (!(battmgr->quirks & QCOM_BATTMGR_QUIRK_NATIVE_USB_ICL) ||
		    !smp_load_acquire(&battmgr->lenovo_read_pending))
			return;
		if (payload_len != sizeof(resp->intval)) {
			battmgr->error = -ENODATA;
			goto out_complete;
		}
		if (le32_to_cpu(resp->intval.property) != READ_ONCE(battmgr->lenovo_property))
			return;
		battmgr->error = le32_to_cpu(resp->intval.result) ? -EIO : 0;
		WRITE_ONCE(battmgr->lenovo_value, le32_to_cpu(resp->intval.value));
		break;
	case BATTMGR_BAT_PROPERTY_GET:''')
table = '\n'.join(f'\t\t{{ "{name}", {number} }},' for name,number in properties.items())
diagnostic = '''/* No writable attribute: all IDs below are native read-only measurements. */
static ssize_t lenovo_charge_diagnostics_show(struct device *dev,
					    struct device_attribute *attr, char *buf)
{
	static const struct {
		const char *name;
		u32 property;
	} fields[] = {
@TABLE@
	};
	struct qcom_battmgr *battmgr = dev_get_drvdata(dev);
	ssize_t count = 0;
	int i, ret;

	if (!(battmgr->quirks & QCOM_BATTMGR_QUIRK_NATIVE_USB_ICL))
		return -EOPNOTSUPP;
	mutex_lock(&battmgr->lock);
	if (!battmgr->service_up) {
		mutex_unlock(&battmgr->lock);
		return -EAGAIN;
	}
	for (i = 0; i < ARRAY_SIZE(fields); i++) {
		WRITE_ONCE(battmgr->lenovo_property, fields[i].property);
		smp_store_release(&battmgr->lenovo_read_pending, true);
		ret = qcom_battmgr_request_property(battmgr,
				BATTMGR_NATIVE_LENOVO_PROPERTY_GET, fields[i].property, 0);
		WRITE_ONCE(battmgr->lenovo_read_pending, false);
		if (ret) {
			count += sysfs_emit_at(buf, count, "%s error %d\\n", fields[i].name, ret);
			if (ret == -ETIMEDOUT || ret == -ECONNRESET)
				break;
		} else {
			count += sysfs_emit_at(buf, count, "%s %d\\n", fields[i].name,
					       (s32)READ_ONCE(battmgr->lenovo_value));
		}
	}
	mutex_unlock(&battmgr->lock);
	return count;
}
static DEVICE_ATTR_RO(lenovo_charge_diagnostics);

static struct attribute *qcom_battmgr_lenovo_attrs[] = {
	&dev_attr_lenovo_charge_diagnostics.attr,
	NULL,
};
static const struct attribute_group qcom_battmgr_lenovo_group = {
	.attrs = qcom_battmgr_lenovo_attrs,
};

'''.replace('@TABLE@',table)
replace('static int qcom_battmgr_probe(struct auxiliary_device *adev,',
        diagnostic+'static int qcom_battmgr_probe(struct auxiliary_device *adev,')
replace('\tif (opcode == BATTMGR_NOTIFICATION)\n\t\tqcom_battmgr_notification(battmgr, data, len);',
        '''\t/* OEM diagnostics share the normal request completion. Ignore unrelated
	 * response/notify opcodes while that read is pending; normal battery
	 * notifications still update their state without completing the read.
	 */
	if ((battmgr->quirks & QCOM_BATTMGR_QUIRK_NATIVE_USB_ICL) &&
	    smp_load_acquire(&battmgr->lenovo_read_pending) &&
	    opcode != BATTMGR_NATIVE_LENOVO_PROPERTY_GET &&
	    opcode != BATTMGR_NOTIFICATION)
		return;
	if (opcode == BATTMGR_NOTIFICATION)
		qcom_battmgr_notification(battmgr, data, len);''')
replace('\tpmic_glink_client_register(battmgr->client);\n\n\treturn 0;',
        '''\tpmic_glink_client_register(battmgr->client);
	dev_set_drvdata(dev, battmgr);
	if (battmgr->quirks & QCOM_BATTMGR_QUIRK_NATIVE_USB_ICL) {
		ret = devm_device_add_group(dev, &qcom_battmgr_lenovo_group);
		if (ret)
			return ret;
	}

	return 0;''')
candidate = work/'qcom_battmgr_pps71.c'
candidate.write_text(text)
(work/'Makefile').write_text('obj-m += qcom_battmgr_pps71.o\n')
sdk = root/'out/kernel-usbc70b'
(sdk/'Module.symvers').write_bytes((sdk/'vmlinux.symvers').read_bytes())
subprocess.run(['make','-C',str(root/'kernel'),'O='+str(sdk),'LOCALVERSION=+',
                '-j2','M='+str(work),'modules'],check=True,
               env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-'))
record = {'status':'OFFLINE_COMPILE_ONLY_NOT_LOADED_OR_IN_BOOT',
          'base_sha256':sha(source),'candidate_sha256':sha(candidate),
          'native_protocol_source_sha256':sha(native),'opcode_read_only':0x60,
          'properties':properties,'serialized_with_existing_battmgr':True,
          'new_pmic_client':False,'charger_writes_added':False,
          'do_not_load_module':'Compilation check only; builtin driver must be updated in a later batched kernel build',
          'remaining':['Native OEM read protocol hardware verification','Locate45W limit using actual PPS/charge-pump readings']}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
