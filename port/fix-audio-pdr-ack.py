#!/usr/bin/env python3
"""Acknowledge a service UP before clients synchronously query that service."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
p = root/'kernel/drivers/soc/qcom/pdr_interface.c'
s = p.read_text()
old = '''\t\tpds = ind->pds;

\t\tmutex_lock(&pdr->status_lock);'''
new = '''\t\tpds = ind->pds;

\t\t/* UP clients may immediately send a synchronous service request.
\t\t * Release the remote service from its indication handshake first.
\t\t * DOWN must still wait until clients release the PD resources.
\t\t */
\t\tif (ind->curr_state == SERVREG_SERVICE_STATE_UP) {
\t\t\tint ret = pdr_send_indack_msg(pdr, pds, ind->transaction_id);

\t\t\tif (!strcmp(pds->service_path, "msm/adsp/audio_pd"))
\t\t\t\tpr_info("TB_AUDIO_PD_UP_ACK ret=%d\\n", ret);
\t\t}

\t\tmutex_lock(&pdr->status_lock);'''
if old in s:
    assert s.count(old) == 1
    s = s.replace(old,new)
else:
    assert new in s
old = '''\t\t/* Ack the indication after clients release the PD resources */
\t\tpdr_send_indack_msg(pdr, pds, ind->transaction_id);'''
new = '''\t\t/* Ack DOWN only after clients release the PD resources. */
\t\tif (ind->curr_state != SERVREG_SERVICE_STATE_UP)
\t\t\tpdr_send_indack_msg(pdr, pds, ind->transaction_id);'''
if old in s:
    s = s.replace(old,new)
else:
    assert new in s
p.write_text(s)
print('PDR UP acknowledgement moved before client initialization; DOWN ordering retained')
