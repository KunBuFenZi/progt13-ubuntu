#!/usr/bin/env python3
"""Expose the existing AudioReach state query for native firmware bring-up."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
path = root/'kernel/sound/soc/qcom/qdsp6/q6apm.c'
text = path.read_text()
old = '\tq6apm_get_apm_state(apm);\n\n\tret = snd_soc_register_component'
new = ('\tret = q6apm_get_apm_state(apm);\n'
       '\tdev_info(dev, "TB378FC_AUDIOREACH_SPF_STATE=%d\\n", ret);\n\n'
       '\tret = snd_soc_register_component')
if 'TB378FC_AUDIOREACH_SPF_STATE=' not in text:
    assert text.count(old) == 1
    path.write_text(text.replace(old,new))
print('AudioReach state observation enabled; protocol and amplifier state unchanged')
