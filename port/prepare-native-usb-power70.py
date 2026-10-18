#!/usr/bin/env python3
"""Generate a per-unit negotiated USB input-current path from the native protocol."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = root / 'kernel/drivers/power/supply/qcom_battmgr.c'
original = source.read_text()
text = original
work = root / 'out/native-usb-power70'
work.mkdir(exist_ok=False)
assert 'lenovo,tb378fc-pmic-glink' in text

def replace(old, new):
    global text
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new)

replace('#define QCOM_BATTMGR_QUIRK_NO_CHARGE_CONTROL\t\tBIT(2)',
        '#define QCOM_BATTMGR_QUIRK_NO_CHARGE_CONTROL\t\tBIT(2)\n'
        '/* TB378FC native USB adapter property and negotiated SDP/CDP/PD ICL. */\n'
        '#define QCOM_BATTMGR_QUIRK_NATIVE_USB_ICL\t\tBIT(3)')
replace('prop = sm8350_usb_prop_map[psp];',
        'prop = sm8350_usb_prop_map[psp];\n'
        '\tif (psp == POWER_SUPPLY_PROP_USB_TYPE &&\n'
        '\t    (battmgr->quirks & QCOM_BATTMGR_QUIRK_NATIVE_USB_ICL))\n'
        '\t\tprop = USB_ADAP_TYPE;')
replace('\t\tcase USB_TYPE:\n\t\t\tbattmgr->usb.usb_type',
        '\t\tcase USB_TYPE:\n\t\tcase USB_ADAP_TYPE:\n\t\t\tbattmgr->usb.usb_type')
replace('\tcase BATTMGR_WLS_PROPERTY_GET:\n\t\tproperty = le32_to_cpu(resp->intval.property);',
        '''\tcase BATTMGR_USB_PROPERTY_SET:
		if (payload_len != sizeof(resp->intval) ||
		    le32_to_cpu(resp->intval.property) != USB_INPUT_CURR_LIMIT) {
			battmgr->error = -ENODATA;
			goto out_complete;
		}
		battmgr->error = le32_to_cpu(resp->intval.result) ? -EIO : 0;
		break;
	case BATTMGR_WLS_PROPERTY_GET:
		property = le32_to_cpu(resp->intval.property);''')
replace('static const enum power_supply_property sm8350_usb_props[] = {',
        '''/* Match the native qti_battery_charger USB property5/opcode0x33.
 * DWC3 provides the speed-capped negotiated draw; no voltage or charge
 * threshold controls are introduced. Other boards remain read-only.
 */
static int qcom_battmgr_usb_is_writeable(struct power_supply *psy,
				      enum power_supply_property psp)
{
	struct qcom_battmgr *battmgr = power_supply_get_drvdata(psy);

	return psp == POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT &&
		(battmgr->quirks & QCOM_BATTMGR_QUIRK_NATIVE_USB_ICL);
}

static int qcom_battmgr_usb_set_property(struct power_supply *psy,
				       enum power_supply_property psp,
				       const union power_supply_propval *val)
{
	struct qcom_battmgr *battmgr = power_supply_get_drvdata(psy);
	int ret;

	if (!qcom_battmgr_usb_is_writeable(psy, psp))
		return -EOPNOTSUPP;
	if (!battmgr->service_up)
		return -EAGAIN;
	if (val->intval < 0 || val->intval > 900000)
		return -EINVAL;

	mutex_lock(&battmgr->lock);
	ret = qcom_battmgr_request_property(battmgr, BATTMGR_USB_PROPERTY_GET,
					  USB_ADAP_TYPE, 0);
	if (ret)
		goto unlock;
	if (battmgr->usb.usb_type != POWER_SUPPLY_USB_TYPE_SDP &&
	    battmgr->usb.usb_type != POWER_SUPPLY_USB_TYPE_CDP &&
	    battmgr->usb.usb_type != POWER_SUPPLY_USB_TYPE_PD) {
		ret = -EOPNOTSUPP;
		goto unlock;
	}
	ret = qcom_battmgr_request_property(battmgr, BATTMGR_USB_PROPERTY_SET,
					  USB_INPUT_CURR_LIMIT, val->intval);
unlock:
	mutex_unlock(&battmgr->lock);
	return ret;
}

static const enum power_supply_property sm8350_usb_props[] = {''')
replace('\t.num_properties = ARRAY_SIZE(sm8350_usb_props),\n\t.get_property = qcom_battmgr_usb_get_property,',
        '\t.num_properties = ARRAY_SIZE(sm8350_usb_props),\n\t.get_property = qcom_battmgr_usb_get_property,\n'
        '\t.set_property = qcom_battmgr_usb_set_property,\n'
        '\t.property_is_writeable = qcom_battmgr_usb_is_writeable,')
replace('QCOM_BATTMGR_QUIRK_NO_BATT_POWER_NOW |\n\t\t\t\t QCOM_BATTMGR_QUIRK_BATT_CURRENT_INVERTED),',
        'QCOM_BATTMGR_QUIRK_NO_BATT_POWER_NOW |\n'
        '\t\t\t\t QCOM_BATTMGR_QUIRK_BATT_CURRENT_INVERTED |\n'
        '\t\t\t\t QCOM_BATTMGR_QUIRK_NATIVE_USB_ICL),')
target = work / 'qcom_battmgr.c'
target.write_text(text)
record = {'status': 'OFFLINE_SOURCE_NOT_DEVICE_TESTED',
          'base_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'candidate_source_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'scope': 'TB378FC only, USB input-current0..900mA, SDP/CDP/PD only; native response validated',
          'native_reference': 'reference/native-peripherals70/qti_battery_charger.c',
          'protocol': {'owner': 32778, 'usb_set_opcode': 51, 'input_current_property': 5,
                       'adapter_type_property': 7},
          'remaining': ['Compile', 'Actual negotiated USB draw request and readback',
                        'Net charge counter over time', 'PD hub/role switch regression']}
(work / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
