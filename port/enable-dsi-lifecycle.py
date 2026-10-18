#!/usr/bin/env python3
"""Keep the DSI video engine off until panel prepare has sent its commands."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / 'kernel/drivers/gpu/drm/msm/dsi/dsi_manager.c'
source = path.read_text()
marker = 'TB378FC_DSI_PREPARE_BEFORE_VIDEO'
if marker not in source:
    pattern = r'static void dsi_mgr_bridge_pre_enable\(struct drm_bridge \*bridge\)\n\{.*?\n\}'
    matches = list(re.finditer(pattern, source, re.S))
    assert len(matches) == 1
    original = matches[0].group()
    power = '''\tret = dsi_mgr_bridge_power_on(bridge);
	if (ret) {
		dev_err(&msm_dsi->pdev->dev, "Power on failed: %d\\n", ret);
		return;
	}

'''
    assert original.count(power) == 1
    enable = original.replace('dsi_mgr_bridge_pre_enable(', 'dsi_mgr_bridge_enable(').replace(power, '')
    pre_enable = '''/* TB378FC_DSI_PREPARE_BEFORE_VIDEO: LP init precedes video streaming. */
static void dsi_mgr_bridge_pre_enable(struct drm_bridge *bridge)
{
	int id = dsi_mgr_bridge_get_id(bridge);
	struct msm_dsi *msm_dsi = dsi_mgr_get_dsi(id);
	int ret;

	if (IS_BONDED_DSI() && !IS_MASTER_DSI_LINK(id))
		return;
	ret = dsi_mgr_bridge_power_on(bridge);
	if (ret)
		dev_err(&msm_dsi->pdev->dev, "Power on failed: %d\\n", ret);
}

'''
    source = source[:matches[0].start()] + pre_enable + enable + source[matches[0].end():]
    pattern = r'static void dsi_mgr_bridge_post_disable\(struct drm_bridge \*bridge\)\n\{.*?\n\}'
    matches = list(re.finditer(pattern, source, re.S))
    assert len(matches) == 1
    original = matches[0].group()
    start = original.index('\tret = msm_dsi_host_disable(host);')
    end = original.index('\tmsm_dsi_host_disable_irq(host);', start)
    disable_body = original[start:end]
    post_disable = original[:start] + original[end:]
    disable = '''static void dsi_mgr_bridge_disable(struct drm_bridge *bridge)
{
	int id = dsi_mgr_bridge_get_id(bridge);
	struct msm_dsi *msm_dsi = dsi_mgr_get_dsi(id);
	struct msm_dsi *msm_dsi1 = dsi_mgr_get_dsi(DSI_1);
	struct mipi_dsi_host *host = msm_dsi->host;
	bool is_bonded_dsi = IS_BONDED_DSI();
	int ret;

	if (is_bonded_dsi && !IS_MASTER_DSI_LINK(id))
		return;

''' + disable_body + '}\n\n'
    source = source[:matches[0].start()] + disable + post_disable + source[matches[0].end():]
    anchor = '\t.pre_enable = dsi_mgr_bridge_pre_enable,'
    assert source.count(anchor) == 1
    source = source.replace(anchor, anchor + '\n\t.enable = dsi_mgr_bridge_enable,\n\t.disable = dsi_mgr_bridge_disable,')
    path.write_text(source)

patch = subprocess.check_output(['git', '-C', str(ROOT / 'kernel'), 'diff', '--',
                                'drivers/gpu/drm/msm/dsi/dsi_manager.c'])
(ROOT / 'out/display-dsi-lifecycle.patch').write_bytes(patch)
print('DISPLAY_DSI_LIFECYCLE_PATCH_INSTALLED')
