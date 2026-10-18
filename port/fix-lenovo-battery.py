#!/usr/bin/env python3
"""Hide a proven-invalid native power field, without changing current or charging."""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--correct-current', action='store_true')
args = p.parse_args()

root = Path(__file__).resolve().parent.parent
source = root/'kernel/drivers/power/supply/qcom_battmgr.c'
text = source.read_text()
anchor = 'static const struct of_device_id qcom_battmgr_of_quirks[] = {\n'
entry = '''	{
		/* TB378FC: reported power is inconsistent with voltage/current. */
		.compatible = "lenovo,tb378fc-pmic-glink",
		.data = (void *)QCOM_BATTMGR_QUIRK_NO_BATT_POWER_NOW,
	},
'''
if '"lenovo,tb378fc-pmic-glink"' not in text:
    assert text.count(anchor) == 1
    source.write_text(text.replace(anchor, anchor+entry))
if args.correct_current:
    text = source.read_text()
    old = ('\t\t.compatible = "lenovo,tb378fc-pmic-glink",\n'
           '\t\t.data = (void *)QCOM_BATTMGR_QUIRK_NO_BATT_POWER_NOW,')
    new = ('\t\t.compatible = "lenovo,tb378fc-pmic-glink",\n'
           '\t\t.data = (void *)(QCOM_BATTMGR_QUIRK_NO_BATT_POWER_NOW |\n'
           '\t\t\t\t QCOM_BATTMGR_QUIRK_BATT_CURRENT_INVERTED),')
    if old in text:
        source.write_text(text.replace(old, new))
    else:
        assert new in text

binding = root/'kernel/Documentation/devicetree/bindings/soc/qcom/qcom,pmic-glink.yaml'
text = binding.read_text()
anchor = "  '#address-cells':\n"
entry = '''      - description:
          Devices whose battery power property does not follow the measured
          battery voltage and current. The standard SoC protocol is otherwise
          retained, including the current sign.
        items:
          - const: lenovo,tb378fc-pmic-glink
          - const: qcom,sm8750-pmic-glink
          - const: qcom,sm8550-pmic-glink
          - const: qcom,pmic-glink

'''
if 'lenovo,tb378fc-pmic-glink' not in text:
    assert text.count(anchor) == 1
    binding.write_text(text.replace(anchor, entry+anchor))
if args.correct_current:
    text = binding.read_text()
    text = text.replace('          retained, including the current sign.\n',
                        '          retained. Native current is positive during discharge.\n')
    binding.write_text(text)
print('TB378FC invalid power hidden; charge controls unchanged; current correction:', args.correct_current)
