#!/usr/bin/env python3
"""Do not issue an APM synchronous request before APR installs its callback."""
from pathlib import Path
import re

root = Path(__file__).resolve().parent.parent
path = root/'kernel/sound/soc/qcom/qdsp6/q6apm.c'
text = path.read_text()
old = ('\tret = q6apm_get_apm_state(apm);\n'
       '\tdev_info(dev, "TB378FC_AUDIOREACH_SPF_STATE=%d\\n", ret);\n')
new = ('\t/* APR installs the receive callback only after this probe returns.\n'
       '\t * PRM and other clients can query SPF once that callback is live.\n'
       '\t */\n')
if old in text:
    text = text.replace(old,new)
elif '\tq6apm_get_apm_state(apm);\n' in text:
    text = text.replace('\tq6apm_get_apm_state(apm);\n',new)
else:
    assert new in text

old = '''bool q6apm_is_adsp_ready(void)
{
	if (g_apm)
		return q6apm_get_apm_state(g_apm);

	return false;
}'''
new = '''bool q6apm_is_adsp_ready(void)
{
	int state;

	if (!g_apm)
		return false;

	state = q6apm_get_apm_state(g_apm);
	dev_info(g_apm->dev, "TB378FC_AUDIOREACH_SPF_STATE=%d\\n", state);
	return state > 0;
}'''
if old in text:
    text = text.replace(old,new)
else:
    assert new in text

query = '''static int q6apm_get_apm_state(struct q6apm *apm)
{
	struct gpr_pkt *pkt __free(kfree) = NULL;
	int ret;

	pkt = audioreach_alloc_apm_cmd_pkt(0, APM_CMD_GET_SPF_STATE, 0);
	if (IS_ERR(pkt))
		return PTR_ERR(pkt);

	ret = q6apm_send_cmd_sync(apm, pkt, APM_CMD_RSP_GET_SPF_STATE);
	if (ret < 0)
		return ret;

	return apm->state;
}'''
text, count = re.subn(r'static int q6apm_get_apm_state\(struct q6apm \*apm\)\n\{.*?\n\}',
                      lambda match: query, text, count=1, flags=re.S)
assert count == 1
path.write_text(text)
print('Deferred initial SPF query to callback-ready clients; errors cannot imply readiness')
