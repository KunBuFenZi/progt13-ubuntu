#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Run once on the tablet as root after choosing the local desktop account.
set -euo pipefail
account=${1:?Usage: setup-owner.sh ACCOUNT}
[[ "$account" =~ ^[a-z_][a-z0-9_-]*\$?$ ]] || { echo 'Invalid local account name' >&2; exit 1; }
getent passwd "$account" >/dev/null
usermod -aG sudo "$account"
# passwd prompts locally; no shared default password is shipped.
passwd "$account"
systemctl unmask snapd.service snapd.socket
systemctl enable --now snapd.socket
systemctl start snapd.service
echo 'Administrator membership and Snap enabled. Log in again for group changes.'
