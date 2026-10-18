# SPDX-License-Identifier: GPL-2.0-only
"""Shared boot policy for temporary images and installed GKI triplets."""

# The firmware advertises PSCI SYSTEM_SUSPEND, so the kernel prefers "deep".
# Deep suspend resumes on this board, but in deep any ADSP message on the
# IPCC/glink interrupts (IRQF_NO_SUSPEND, never armed as wakeups) completes a
# full resume, which made earlier tests wake early. s2idle handles such
# interrupts without leaving suspend, and the other SM8750-class tablet
# ships it as well.
CMDLINE = 'rdinit=/init panic=15 erhai.boot=mainline-dev mem_sleep_default=s2idle'

# Display blanking is backlight-only in the device package. No experimental
# touch or DSI retention kernel parameters are needed.
PROFILE_EXTRA = {
    'desktop': (
        'erhai.watchdog=900 erhai.session=5400 '
        'erhai.switchroot=1'
    ),
    # The watchdog bounds initramfs. Persistent sessions do not expire.
    'persistent': (
        'erhai.watchdog=600 erhai.root=PARTLABEL=linux_rootfs loglevel=4'
    ),
}
