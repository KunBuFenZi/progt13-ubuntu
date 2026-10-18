#!/usr/bin/env python3
"""Trace only the SPF readiness request, without changing APR ordering."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
p = root/'kernel/drivers/soc/qcom/apr.c'
s = p.read_text()
if 'TB_SPF_SEND' not in s:
    s = s.replace('#include <linux/kernel.h>', '#include <linux/kernel.h>\n#include <linux/sched.h>')
    old = '\thdr = &pkt->hdr;\n\n\tspin_lock_irqsave(&svc->lock, flags);'
    new = '''\thdr = &pkt->hdr;
\tif (hdr->opcode == 0x01001021)
\t\tdev_info(pr->dev, "TB_SPF_SEND src=%x dst=%x callback=%ps task=%s pid=%d\\n",
\t\t\t hdr->src_port, hdr->dest_port, svc->callback, current->comm, current->pid);

\tspin_lock_irqsave(&svc->lock, flags);'''
    assert s.count(old) == 1
    s = s.replace(old,new)
    old = '\tabuf->len = len;\n\tmemcpy(abuf->buf, buf, len);'
    new = '''\tif (apr->type == PR_TYPE_GPR && len >= sizeof(struct gpr_hdr)) {
\t\tstruct gpr_hdr *hdr = buf;

\t\tif (hdr->opcode == 0x02001007)
\t\t\tdev_info(apr->dev, "TB_SPF_RX_ENQUEUED dst=%x task=%s pid=%d\\n",
\t\t\t\t hdr->dest_port, current->comm, current->pid);
\t}
\tabuf->len = len;
\tmemcpy(abuf->buf, buf, len);'''
    assert s.count(old) == 1
    s = s.replace(old,new)
    old = '\tif (svc->callback)\n\t\tsvc->callback(&resp, svc->priv, 0);'
    new = '''\tif (hdr->opcode == 0x02001007)
\t\tdev_info(gpr->dev, "TB_SPF_RX_DISPATCH dst=%x callback=%ps task=%s\\n",
\t\t\t hdr->dest_port, svc->callback, current->comm);
\tif (svc->callback)
\t\tsvc->callback(&resp, svc->priv, 0);'''
    assert s.count(old) == 1
    s = s.replace(old,new)
    p.write_text(s)
print('SPF-only transport trace installed; protocol and callback ordering unchanged')
