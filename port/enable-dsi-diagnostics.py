#!/usr/bin/env python3
"""Capture DSI register state at the timeout, before the host restores CTRL."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / 'kernel/drivers/gpu/drm/msm/dsi/dsi_host.c'
source = path.read_text()
if 'TB_DSI_TIMEOUT' not in source:
    anchor = '''\t\tif (ret == 0)
			ret = -ETIMEDOUT;
		else
			ret = len;'''
    assert source.count(anchor) == 1
    replacement = '''\t\tif (ret == 0) {
			pr_err("TB_DSI_TIMEOUT id=%d enabled=%d ctrl=%08x status=%08x intr=%08x fifo=%08x lane=%08x trigger=%08x dma=%08x base=%08x len=%08x phyerr=%08x timeout=%08x clk=%08x\\n",
			       msm_host->id, msm_host->enabled,
			       dsi_read(msm_host, REG_DSI_CTRL),
			       dsi_read(msm_host, REG_DSI_STATUS0),
			       dsi_read(msm_host, REG_DSI_INTR_CTRL),
			       dsi_read(msm_host, REG_DSI_FIFO_STATUS),
			       dsi_read(msm_host, REG_DSI_LANE_STATUS),
			       dsi_read(msm_host, REG_DSI_TRIG_CTRL),
			       dsi_read(msm_host, REG_DSI_CMD_DMA_CTRL),
			       dsi_read(msm_host, REG_DSI_DMA_BASE),
			       dsi_read(msm_host, REG_DSI_DMA_LEN),
			       dsi_read(msm_host, REG_DSI_DLN0_PHY_ERR),
			       dsi_read(msm_host, REG_DSI_TIMEOUT_STATUS),
			       dsi_read(msm_host, REG_DSI_CLK_STATUS));
			ret = -ETIMEDOUT;
		} else {
			ret = len;
		}'''
    path.write_text(source.replace(anchor, replacement))
patch = subprocess.check_output(['git', '-C', str(ROOT / 'kernel'), 'diff', '--',
                                'drivers/gpu/drm/msm/dsi/dsi_host.c'])
(ROOT / 'out/display-dsi-diagnostics.patch').write_bytes(patch)
print('DISPLAY_DSI_TIMEOUT_DIAGNOSTICS_INSTALLED')
