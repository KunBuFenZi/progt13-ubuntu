#!/usr/bin/env python3
"""Match the native v2.8+ DSI command DMA VBIF priority setting.

Authoritative local msm_drm.ko dsi_ctrl_hw_cmn_kickoff_command sets bits 2:0
at physical register offset 0x1cc. Upstream's 6G ctrl_base already adds 4,
so the register XML offset is 0x1c8. Public Qualcomm source independently
names the register DSI_VBIF_CTRL and the priority value 7.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
xml = ROOT / 'kernel/drivers/gpu/drm/msm/registers/display/dsi.xml'
source = xml.read_text()
if 'name="VBIF_CTRL"' not in source:
    anchor = '\t<reg32 offset="0x00128" name="PHY_RESET">'
    assert source.count(anchor) == 1
    source = source.replace(anchor, '\t<reg32 offset="0x001c8" name="VBIF_CTRL"/>\n\n' + anchor)
    xml.write_text(source)

path = ROOT / 'kernel/drivers/gpu/drm/msm/dsi/dsi_host.c'
source = path.read_text()
if 'TB_DSI_VBIF_PRIORITY' not in source:
    anchor = '\tdsi_write(msm_host, REG_DSI_DMA_BASE, dma_base);'
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''\t/* TB_DSI_VBIF_PRIORITY: native v2.8+ command DMA arbitration. */
	if (msm_dsi_host_version_geq(msm_host, MSM_DSI_VER_MAJOR_6G,
				     MSM_DSI_6G_VER_MINOR_V2_8_0)) {
		u32 vbif = dsi_read(msm_host, REG_DSI_VBIF_CTRL);

		dsi_write(msm_host, REG_DSI_VBIF_CTRL, vbif | 0x7);
		if ((vbif & 0x7) != 0x7)
			pr_info("TB_DSI_VBIF id=%d old=%08x new=%08x\\n",
				msm_host->id, vbif, dsi_read(msm_host, REG_DSI_VBIF_CTRL));
	}

''' + anchor)
    path.write_text(source)
patch = subprocess.check_output(['git', '-C', str(ROOT / 'kernel'), 'diff', '--',
                                'drivers/gpu/drm/msm/dsi/dsi_host.c',
                                'drivers/gpu/drm/msm/registers/display/dsi.xml'])
(ROOT / 'out/display-dsi-vbif.patch').write_bytes(patch)
print('DISPLAY_DSI_VBIF_PRIORITY_INSTALLED')
