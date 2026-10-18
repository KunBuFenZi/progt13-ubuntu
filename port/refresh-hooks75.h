/* SPDX-License-Identifier: GPL-2.0 */
/* Included by the isolated refresh trial, never by the frozen panel driver. */
#include <linux/io.h>
#include <linux/debugfs.h>
#include <linux/seq_file.h>
#include <drm/drm_atomic.h>
#include <drm/drm_bridge.h>
#include <drm/drm_encoder.h>
#include <drm/drm_mipi_dsi.h>
#include "dsi.xml.h"

/* Register addresses in Lenovo's dsi_ctrl_reg.h include the 6G +4 shift.
 * The mainline host's ctrl_base already includes it. */
#define TIMING_DB75 (0x1e8 - 4)
#define TIMING_FLUSH75 (0x1e4 - 4)
struct host_prefix75 {
	struct mipi_dsi_host base;
	struct platform_device *pdev;
	struct drm_device *dev;
	int id;
	void __iomem *ctrl_base;
};
/* Exact complete msm_dsi layout from dsi.h, without snapshot internals. */
struct dsi_prefix75 {
	struct drm_device *dev;
	struct platform_device *pdev;
	struct mipi_dsi_host *host;
	void *phy;
	const char *te_source;
	struct drm_bridge *next_bridge;
	struct device *phy_dev;
	bool phy_enabled;
	int id;
};
static struct platform_device *dsi_devices75[2];
static struct host_prefix75 *hosts75[2];
static struct drm_bridge *dsi_bridge75, *panel_bridge75;
static const struct drm_bridge_funcs *dsi_original75, *panel_original75;
static struct drm_bridge_funcs dsi_funcs75, panel_funcs75;
static u32 active_width75, original_db75[2];
static struct dentry *debug75;
static bool armed;
module_param(armed, bool, 0600);
MODULE_PARM_DESC(armed, "Preserve the running links only during same-size refresh changes");

static bool native_mode75(const struct drm_display_mode *m)
{
	int hz = drm_mode_vrefresh(m);
	return m->hdisplay == 3504 && m->vdisplay == 2190 &&
		(hz == 60 || hz == 120 || hz == 144);
}

static struct drm_crtc_state *live_change75(struct drm_bridge *b, struct drm_atomic_commit *commit)
{
	struct drm_crtc *crtc;
	struct drm_crtc_state *old, *new;
	if (!READ_ONCE(armed))
		return NULL;
	crtc = drm_atomic_get_new_crtc_for_encoder(commit, b->encoder);
	if (!crtc || crtc != drm_atomic_get_old_crtc_for_encoder(commit, b->encoder))
		return NULL;
	old = drm_atomic_get_old_crtc_state(commit, crtc);
	new = drm_atomic_get_new_crtc_state(commit, crtc);
	if (!old || !new || !old->active || !new->active || !new->mode_changed ||
	    !native_mode75(&old->adjusted_mode) || !native_mode75(&new->adjusted_mode))
		return NULL;
	return new;
}

static void update_timing75(const struct drm_display_mode *m)
{
	u32 ht = m->htotal / 2 - m->hdisplay / 2 + active_width75;
	u32 hs = (m->htotal - m->hsync_start) / 2;
	u32 vs = m->vtotal - m->vsync_start;
	int i;
	/* The proven active payload width includes the running DSC/widebus
	 * conversion. Only porch/sync/total values change; DSC stays intact.
	 * Native order: clock master DSI0, then DSI1. */
	for (i = 0; i < 2; i++) {
		void __iomem *p = hosts75[i]->ctrl_base;
		writel(1, p + TIMING_DB75);
		wmb();
		writel(DSI_ACTIVE_H_START(hs) | DSI_ACTIVE_H_END(hs + active_width75), p + REG_DSI_ACTIVE_H);
		writel(DSI_ACTIVE_V_START(vs) | DSI_ACTIVE_V_END(vs + m->vdisplay), p + REG_DSI_ACTIVE_V);
		writel(DSI_TOTAL_H_TOTAL(ht - 1) | DSI_TOTAL_V_TOTAL(m->vtotal - 1), p + REG_DSI_TOTAL);
		writel(DSI_ACTIVE_HSYNC_END((m->hsync_end - m->hsync_start) / 2), p + REG_DSI_ACTIVE_HSYNC);
		writel(0, p + REG_DSI_ACTIVE_VSYNC_HPOS);
		writel(DSI_ACTIVE_VSYNC_VPOS_END(m->vsync_end - m->vsync_start), p + REG_DSI_ACTIVE_VSYNC_VPOS);
		wmb();
		writel(1, p + TIMING_FLUSH75);
		readl(p + TIMING_FLUSH75);
	}
	pr_info("TB378FC_REFRESH75 timing update %dHz HT=%u VT=%u, links retained\n", drm_mode_vrefresh(m), ht, m->vtotal);
}

static void dsi_post_disable75(struct drm_bridge *b, struct drm_atomic_commit *commit)
{
	int i;
	if (live_change75(b, commit))
		return;
	for (i = 0; i < 2; i++)
		writel(original_db75[i], hosts75[i]->ctrl_base + TIMING_DB75);
	dsi_original75->post_disable(b);
}
static void dsi_pre_enable75(struct drm_bridge *b, struct drm_atomic_commit *commit)
{
	struct drm_crtc_state *new = live_change75(b, commit);
	if (new)
		update_timing75(&new->adjusted_mode);
	else
		dsi_original75->pre_enable(b);
}
static void panel_post_disable75(struct drm_bridge *b, struct drm_atomic_commit *commit)
{
	if (!live_change75(b, commit))
		panel_original75->atomic_post_disable(b, commit);
}
static void panel_pre_enable75(struct drm_bridge *b, struct drm_atomic_commit *commit)
{
	if (!live_change75(b, commit))
		panel_original75->atomic_pre_enable(b, commit);
}

static int refresh_state75_show(struct seq_file *s, void *unused)
{
	int i;
	seq_printf(s, "armed=%d active_width=%u\n", armed, active_width75);
	for (i = 0; i < 2; i++) {
		void __iomem *p = hosts75[i]->ctrl_base;
		seq_printf(s, "dsi%d ctrl=%#x h=%#x v=%#x total=%#x db=%#x flush=%#x\n", i,
			readl(p + REG_DSI_CTRL), readl(p + REG_DSI_ACTIVE_H), readl(p + REG_DSI_ACTIVE_V),
			readl(p + REG_DSI_TOTAL), readl(p + TIMING_DB75), readl(p + TIMING_FLUSH75));
	}
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(refresh_state75);

/* Called with DRM modeset locks held. Does not change the display mode. */
static int install_hooks75(void)
{
	const char *paths[] = {"/soc@0/display-subsystem@ae00000/dsi@ae94000",
		"/soc@0/display-subsystem@ae00000/dsi@ae96000"};
	struct dsi_prefix75 *dsi;
	struct device_node *np;
	u32 h, ht, vt;
	int i, ret = -ENODEV;
	for (i = 0; i < 2; i++) {
		np = of_find_node_by_path(paths[i]);
		if (!np)
			goto fail;
		dsi_devices75[i] = of_find_device_by_node(np);
		of_node_put(np);
		if (!dsi_devices75[i])
			goto fail;
		dsi = platform_get_drvdata(dsi_devices75[i]);
		if (!dsi || dsi->id != i || !dsi->host)
			goto fail;
		hosts75[i] = (void *)dsi->host;
		if (hosts75[i]->pdev != dsi_devices75[i] || hosts75[i]->dev != tablet_drm || hosts75[i]->id != i)
			goto fail;
		if (dsi->next_bridge && dsi->next_bridge->encoder) {
			if (panel_bridge75 && panel_bridge75 != dsi->next_bridge)
				goto fail;
			panel_bridge75 = dsi->next_bridge;
		}
		h = readl(hosts75[i]->ctrl_base + REG_DSI_ACTIVE_H);
		ht = (readl(hosts75[i]->ctrl_base + REG_DSI_TOTAL) & 0xffff) + 1;
		vt = (readl(hosts75[i]->ctrl_base + REG_DSI_TOTAL) >> 16) + 1;
		pr_info("TB378FC_REFRESH75 dsi%d h=%#x ht=%u vt=%u ctrl=%#x\n", i,h,ht,vt,readl(hosts75[i]->ctrl_base + REG_DSI_CTRL));
		if ((h & 0xffff) != 80 || vt != 2440 || !(readl(hosts75[i]->ctrl_base + REG_DSI_CTRL) & DSI_CTRL_ENABLE))
			goto fail;
		if (i == 0)
			active_width75 = (h >> 16) - (h & 0xffff);
		if ((h >> 16) - (h & 0xffff) != active_width75 || ht != 157 + active_width75)
			goto fail;
		original_db75[i] = readl(hosts75[i]->ctrl_base + TIMING_DB75);
	}
	if (!panel_bridge75)
		goto fail;
	dsi_bridge75 = drm_bridge_get_prev_bridge(panel_bridge75);
	if (!dsi_bridge75)
		goto fail;
	dsi_original75 = dsi_bridge75->funcs;
	panel_original75 = panel_bridge75->funcs;
	if (!dsi_original75->pre_enable || !dsi_original75->post_disable ||
	    dsi_original75->atomic_pre_enable || dsi_original75->atomic_post_disable ||
	    !panel_original75->atomic_pre_enable || !panel_original75->atomic_post_disable)
		goto fail;
	dsi_funcs75 = *dsi_original75;
	dsi_funcs75.pre_enable = NULL;
	dsi_funcs75.post_disable = NULL;
	dsi_funcs75.atomic_pre_enable = dsi_pre_enable75;
	dsi_funcs75.atomic_post_disable = dsi_post_disable75;
	panel_funcs75 = *panel_original75;
	panel_funcs75.atomic_pre_enable = panel_pre_enable75;
	panel_funcs75.atomic_post_disable = panel_post_disable75;
	WRITE_ONCE(dsi_bridge75->funcs, &dsi_funcs75);
	WRITE_ONCE(panel_bridge75->funcs, &panel_funcs75);
	debug75 = debugfs_create_dir("tb378fc-refresh75", NULL);
	debugfs_create_file("state", 0400, debug75, NULL, &refresh_state75_fops);
	return 0;
fail:
	if (dsi_bridge75) {
		drm_bridge_put(dsi_bridge75);
		dsi_bridge75 = NULL;
	}
	for (i = 0; i < 2; i++)
		if (dsi_devices75[i]) {
			put_device(&dsi_devices75[i]->dev);
			dsi_devices75[i] = NULL;
		}
	return ret;
}

static void remove_hooks75(void)
{
	int i;
	WRITE_ONCE(dsi_bridge75->funcs, dsi_original75);
	WRITE_ONCE(panel_bridge75->funcs, panel_original75);
	for (i = 0; i < 2; i++) {
		writel(original_db75[i], hosts75[i]->ctrl_base + TIMING_DB75);
		put_device(&dsi_devices75[i]->dev);
	}
	drm_bridge_put(dsi_bridge75);
	debugfs_remove_recursive(debug75);
}
