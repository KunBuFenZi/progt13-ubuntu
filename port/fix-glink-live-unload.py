#!/usr/bin/env python3
"""Avoid recursive removal of a primary rpmsg device while its mutex is held."""
from pathlib import Path

path = Path('kernel/drivers/rpmsg/qcom_glink_native.c')
text = path.read_text()
old = '''\t/* Decouple the potential rpdev from the channel */
\tqcom_glink_remove_rpmsg_device(glink, channel);

\tqcom_glink_send_close_req(glink, channel);'''
new = '''\t/* TB378FC_LIVE_UNLOAD: rpmsg_dev_remove() invokes destroy_ept with
\t * this primary device's mutex held. Unregistering it here recurses
\t * into device_del() and deadlocks. The close/close-ack receive paths
\t * already own primary-device removal after this callback returns.
\t */
\tqcom_glink_send_close_req(glink, channel);'''
if old in text:
    assert text.count(old) == 1
    text = text.replace(old, new)
else:
    assert new in text
old = '''\tif (channel->rpdev) {
\t\tstrscpy_pad(chinfo.name, channel->name, sizeof(chinfo.name));
\t\tchinfo.src = RPMSG_ADDR_ANY;
\t\tchinfo.dst = RPMSG_ADDR_ANY;
\t\trpmsg_unregister_device(glink->dev, &chinfo);
\t}
\tchannel->rpdev = NULL;'''
new = '''\t/* Claim removal before unregister can trigger callbacks or a second close. */
\tif (xchg(&channel->rpdev, NULL)) {
\t\tstrscpy_pad(chinfo.name, channel->name, sizeof(chinfo.name));
\t\tchinfo.src = RPMSG_ADDR_ANY;
\t\tchinfo.dst = RPMSG_ADDR_ANY;
\t\trpmsg_unregister_device(glink->dev, &chinfo);
\t}'''
if old in text:
    assert text.count(old) == 1
    text = text.replace(old, new)
else:
    assert new in text
path.write_text(text)
print('GLINK recursive primary-device removal fix applied; requires next kernel to test')
