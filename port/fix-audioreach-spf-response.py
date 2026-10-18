#!/usr/bin/env python3
"""Handle a basic error reply to GET_SPF_STATE instead of waiting five seconds."""
from pathlib import Path
import re

root = Path(__file__).resolve().parent.parent
# The UP-before-callback hypothesis did not change the timeout in attempt44.
# Restore the original PDR protocol ordering; do not retain an ineffective fix.
p = root/'kernel/drivers/soc/qcom/pdr_interface.c'
s = p.read_text()
s, n = re.subn(r'\n\t\t/\* UP clients may immediately send.*?\n\t\t}\n', '',s,count=1,flags=re.S)
if n:
    s = s.replace('''\t\t/* Ack DOWN only after clients release the PD resources. */
\t\tif (ind->curr_state != SERVREG_SERVICE_STATE_UP)
\t\t\tpdr_send_indack_msg(pdr, pds, ind->transaction_id);''','''\t\t/* Ack the indication after clients release the PD resources */
\t\tpdr_send_indack_msg(pdr, pds, ind->transaction_id);''')
    p.write_text(s)
assert 'TB_AUDIO_PD_UP_ACK' not in s

p = root/'kernel/sound/soc/qcom/qdsp6/q6apm.c'
whole = p.read_text()
offset = whole.index('static int apm_callback(')
s = whole[offset:]
old = '''\tcase GPR_BASIC_RSP_RESULT:
\t\tswitch (result->opcode) {
\t\tcase APM_CMD_SHARED_MEM_MAP_REGIONS:'''
new = '''\tcase GPR_BASIC_RSP_RESULT:
\t\tif (result->opcode == APM_CMD_GET_SPF_STATE)
\t\t\tdev_info(dev, "TB_SPF_BASIC_RESPONSE status=%u\\n", result->status);
\t\tswitch (result->opcode) {
\t\tcase APM_CMD_GET_SPF_STATE:
\t\tcase APM_CMD_SHARED_MEM_MAP_REGIONS:'''
if old in s:
    assert s.count(old) == 1
    s = s.replace(old,new)
else:
    assert new in s
p.write_text(whole[:offset]+s)
print('SPF basic replies handled; ineffective PDR ordering change reverted')
