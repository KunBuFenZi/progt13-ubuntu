/* SPDX-License-Identifier: GPL-2.0-only */
/* Isolated native DFPS trial: retain DPU, DSC, panel, PHY and DSI engines. */
#include <linux/io.h>
#include <linux/debugfs.h>
#include <linux/pm_runtime.h>
#include <linux/seq_file.h>
#include <drm/drm_atomic.h>
#include <drm/drm_bridge.h>
#include <drm/drm_modeset_helper_vtables.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_vblank.h>
#include "disp/dpu1/dpu_encoder_phys.h"
#include "dsi.xml.h"

#define TIMING_DB76 (0x1e8 - 4)
#define TIMING_FLUSH76 (0x1e4 - 4)
struct host_prefix76 {
	struct mipi_dsi_host base;
	struct platform_device *pdev;
	struct drm_device *dev;
	int id;
	void __iomem *ctrl_base;
};
struct dsi_prefix76 {
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
/* Exact prefix of the pinned dpu_encoder.c; validate every referenced phys. */
struct encoder_prefix76 {
	struct drm_encoder base;
	spinlock_t enc_spinlock;
	bool enabled;
	bool commit_done_timedout;
	unsigned int num_phys_encs;
	struct dpu_encoder_phys *phys_encs[4];
	struct dpu_encoder_phys *cur_master;
	struct dpu_encoder_phys *cur_slave;
};
static struct platform_device *dsi_devices76[2];
static struct host_prefix76 *hosts76[2];
static struct drm_bridge *dsi_bridge76;
static struct drm_crtc *crtc76;
static struct encoder_prefix76 *encoder76;
static const struct drm_crtc_helper_funcs *original_crtc76;
static struct drm_crtc_helper_funcs crtc_funcs76;
static u32 active_width76, original_db76[2];
static struct dentry *debug76;
static atomic_t applied76 = ATOMIC_INIT(0);
static bool armed, expose144;
module_param(armed, bool, 0600);
module_param(expose144, bool, 0400);
MODULE_PARM_DESC(armed, "Allow checked same-topology continuous timing updates");
MODULE_PARM_DESC(expose144, "Also enumerate native 144Hz; default trial is 60/120 only");

static bool native_mode76(const struct drm_display_mode *m)
{
	if (m->hdisplay != 3504 || m->vdisplay != 2190 || m->flags)
		return false;
	if (m->clock == 1117910 && m->hsync_start == 3658 &&
	    m->hsync_end == 3690 && m->htotal == 3818) {
		return (m->vsync_start == 2216 && m->vsync_end == 2220 && m->vtotal == 2440) ||
		       (m->vsync_start == 4656 && m->vsync_end == 4660 && m->vtotal == 4880);
	}
	return expose144 && m->clock == 1205533 && m->hsync_start == 3624 &&
		m->hsync_end == 3656 && m->htotal == 3688 && m->vsync_start == 2216 &&
		m->vsync_end == 2220 && m->vtotal == 2270;
}

static bool timing_change76(const struct drm_crtc_state *old,
			    const struct drm_crtc_state *new)
{
	return old && new && old->active && new->active && old->enable && new->enable &&
		old->encoder_mask == new->encoder_mask && hweight32(new->encoder_mask) == 1 &&
		!new->active_changed && !new->connectors_changed && !new->color_mgmt_changed &&
		native_mode76(&old->adjusted_mode) && native_mode76(&new->adjusted_mode) &&
		!drm_mode_equal(&old->adjusted_mode, &new->adjusted_mode);
}

static bool physical_ready76(const struct drm_display_mode *old_mode)
{
	int i;
	if (!encoder76 || !encoder76->enabled || encoder76->num_phys_encs != 2 ||
	    !encoder76->cur_master || !encoder76->cur_slave)
		return false;
	for (i = 0; i < 2; i++) {
		struct dpu_encoder_phys *p = encoder76->phys_encs[i];
		if (!p || p->parent != &encoder76->base || !p->hw_intf || !p->hw_ctl ||
		    p->hw_intf->cap->type != INTF_DSI || p->enable_state != DPU_ENC_ENABLED ||
		    !p->ops.enable || !drm_mode_equal(&p->cached_mode, old_mode))
			return false;
	}
	return true;
}

static int check76(struct drm_crtc *crtc, struct drm_atomic_commit *commit)
{
	struct drm_crtc_state *old = drm_atomic_get_old_crtc_state(commit, crtc);
	struct drm_crtc_state *new = drm_atomic_get_new_crtc_state(commit, crtc);
	struct dpu_crtc_state *oc, *nc;
	int ret, i;
	bool change = timing_change76(old, new);
	if (change && (!READ_ONCE(armed) || !physical_ready76(&old->adjusted_mode)))
		return -EINVAL;
	ret = original_crtc76->atomic_check(crtc, commit);
	if (ret || !change)
		return ret;
	oc = to_dpu_crtc_state(old);
	nc = to_dpu_crtc_state(new);
	/* Reuse only precisely the same already running mixer/CTL topology. */
	if (oc->num_mixers != nc->num_mixers || oc->num_ctls != nc->num_ctls)
		return -EINVAL;
	for (i = 0; i < oc->num_mixers; i++)
		if (oc->mixers[i].hw_lm != nc->mixers[i].hw_lm ||
		    oc->mixers[i].lm_ctl != nc->mixers[i].lm_ctl ||
		    oc->mixers[i].hw_dspp != nc->mixers[i].hw_dspp)
			return -EINVAL;
	for (i = 0; i < oc->num_ctls; i++)
		if (oc->hw_ctls[i] != nc->hw_ctls[i])
			return -EINVAL;
	/* Generic mode comparison has run; apply this timing in atomic_flush. */
	new->mode_changed = false;
	return 0;
}

static void flush76(struct drm_crtc *crtc, struct drm_atomic_commit *commit)
{
	struct drm_crtc_state *old = drm_atomic_get_old_crtc_state(commit, crtc);
	struct drm_crtc_state *new = drm_atomic_get_new_crtc_state(commit, crtc);
	const struct drm_display_mode *m;
	u32 ht, hs, vs;
	int i;
	original_crtc76->atomic_flush(crtc, commit);
	if (!timing_change76(old, new) || new->mode_changed)
		return;
	m = &new->adjusted_mode;
	/* Keep host software mode caches correct for later ordinary DPMS. */
	dsi_bridge76->funcs->mode_set(dsi_bridge76, &new->mode, m);
	ht = m->htotal / 2 - m->hdisplay / 2 + active_width76;
	hs = (m->htotal - m->hsync_start) / 2;
	vs = m->vtotal - m->vsync_start;
	for (i = 0; i < 2; i++) {
		void __iomem *p = hosts76[i]->ctrl_base;
		/* Native clock master first; both controllers use Timing DB. */
		writel(1, p + TIMING_DB76);
		writel(DSI_ACTIVE_H_START(hs) | DSI_ACTIVE_H_END(hs + active_width76), p + REG_DSI_ACTIVE_H);
		writel(DSI_ACTIVE_V_START(vs) | DSI_ACTIVE_V_END(vs + m->vdisplay), p + REG_DSI_ACTIVE_V);
		writel(DSI_TOTAL_H_TOTAL(ht - 1) | DSI_TOTAL_V_TOTAL(m->vtotal - 1), p + REG_DSI_TOTAL);
		writel(DSI_ACTIVE_HSYNC_END((m->hsync_end - m->hsync_start) / 2), p + REG_DSI_ACTIVE_HSYNC);
		writel(0, p + REG_DSI_ACTIVE_VSYNC_HPOS);
		writel(DSI_ACTIVE_VSYNC_VPOS_END(m->vsync_end - m->vsync_start), p + REG_DSI_ACTIVE_VSYNC_VPOS);
		wmb();
		writel(1, p + TIMING_FLUSH76);
	}
	for (i = 0; i < 2; i++)
		encoder76->phys_encs[i]->cached_mode = *m;
	/* Reuse the real timing/prefetch programmer. On an ENABLED encoder it
	 * does not stop/start the timing engine or change its enable_state.
	 * Its pending INTF flush joins the regular atomic plane kickoff. */
	encoder76->cur_slave->ops.enable(encoder76->cur_slave);
	encoder76->cur_master->ops.enable(encoder76->cur_master);
	drm_calc_timestamping_constants(crtc, m);
	atomic_inc(&applied76);
	pr_info("TB378FC_REFRESH76 continuous %dHz ht=%u vt=%u engines retained\n",
		drm_mode_vrefresh(m), ht, m->vtotal);
}

static int state76_show(struct seq_file *s, void *unused)
{
	int i;
	seq_printf(s, "armed=%d expose144=%d applied=%d active_width=%u\n",
		armed, expose144, atomic_read(&applied76), active_width76);
	for (i = 0; i < 2; i++) {
		struct device *dev = &dsi_devices76[i]->dev;
		if (pm_runtime_get_if_in_use(dev) > 0) {
			void __iomem *p = hosts76[i]->ctrl_base;
			seq_printf(s, "dsi%d ctrl=%#x total=%#x db=%#x\n", i,
				readl(p + REG_DSI_CTRL), readl(p + REG_DSI_TOTAL), readl(p + TIMING_DB76));
			pm_runtime_put(dev);
		} else {
			seq_printf(s, "dsi%d powered_down\n", i);
		}
	}
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(state76);

static int install_hooks76(void)
{
	const char *paths[] = {"/soc@0/display-subsystem@ae00000/dsi@ae94000",
		"/soc@0/display-subsystem@ae00000/dsi@ae96000"};
	struct drm_connector_list_iter iter;
	struct drm_connector *conn;
	struct drm_encoder *enc;
	struct drm_bridge *panel_bridge = NULL;
	struct device_node *np;
	struct dsi_prefix76 *dsi;
	u32 h, ht, vt;
	int i, ret = -ENODEV;
	for (i = 0; i < 2; i++) {
		np = of_find_node_by_path(paths[i]);
		if (!np) goto fail;
		dsi_devices76[i] = of_find_device_by_node(np);
		of_node_put(np);
		if (!dsi_devices76[i]) goto fail;
		dsi = platform_get_drvdata(dsi_devices76[i]);
		if (!dsi || dsi->id != i || !dsi->host) goto fail;
		hosts76[i] = (void *)dsi->host;
		if (hosts76[i]->pdev != dsi_devices76[i] || hosts76[i]->dev != tablet_drm || hosts76[i]->id != i)
			goto fail;
		if (dsi->next_bridge && dsi->next_bridge->encoder)
			panel_bridge = dsi->next_bridge;
		h = readl(hosts76[i]->ctrl_base + REG_DSI_ACTIVE_H);
		ht = (readl(hosts76[i]->ctrl_base + REG_DSI_TOTAL) & 0xffff) + 1;
		vt = (readl(hosts76[i]->ctrl_base + REG_DSI_TOTAL) >> 16) + 1;
		if ((h & 0xffff) != 80 || vt != 2440 || !(readl(hosts76[i]->ctrl_base + REG_DSI_CTRL) & DSI_CTRL_ENABLE))
			goto fail;
		if (!i) active_width76 = (h >> 16) - (h & 0xffff);
		if (active_width76 != 468 || (h >> 16) - (h & 0xffff) != active_width76 || ht != 625)
			goto fail;
		original_db76[i] = readl(hosts76[i]->ctrl_base + TIMING_DB76);
	}
	if (!panel_bridge) goto fail;
	dsi_bridge76 = drm_bridge_get_prev_bridge(panel_bridge);
	if (!dsi_bridge76 || !dsi_bridge76->funcs->mode_set) goto fail;
	drm_connector_list_iter_begin(tablet_drm, &iter);
	drm_for_each_connector_iter(conn, &iter)
		if (conn->connector_type == DRM_MODE_CONNECTOR_DSI && conn->state)
			crtc76 = conn->state->crtc;
	drm_connector_list_iter_end(&iter);
	if (!crtc76 || !crtc76->state->active || !native_mode76(&crtc76->state->adjusted_mode))
		goto fail;
	drm_for_each_encoder_mask(enc, tablet_drm, crtc76->state->encoder_mask) {
		if (encoder76 || enc->encoder_type != DRM_MODE_ENCODER_DSI) goto fail;
		encoder76 = (void *)enc;
	}
	if (!physical_ready76(&crtc76->state->adjusted_mode)) goto fail;
	original_crtc76 = crtc76->helper_private;
	if (!original_crtc76->atomic_check || !original_crtc76->atomic_flush) goto fail;
	if (crtc76->state->commit && drm_crtc_commit_wait(crtc76->state->commit)) goto fail;
	crtc_funcs76 = *original_crtc76;
	crtc_funcs76.atomic_check = check76;
	crtc_funcs76.atomic_flush = flush76;
	WRITE_ONCE(crtc76->helper_private, &crtc_funcs76);
	debug76 = debugfs_create_dir("tb378fc-refresh76", NULL);
	debugfs_create_file("state", 0400, debug76, NULL, &state76_fops);
	return 0;
fail:
	if (dsi_bridge76) { drm_bridge_put(dsi_bridge76); dsi_bridge76 = NULL; }
	for (i = 0; i < 2; i++)
		if (dsi_devices76[i]) { put_device(&dsi_devices76[i]->dev); dsi_devices76[i] = NULL; }
	return ret;
}

static void remove_hooks76(void)
{
	int i;
	if (crtc76->state->commit) drm_crtc_commit_wait(crtc76->state->commit);
	WRITE_ONCE(crtc76->helper_private, original_crtc76);
	for (i = 0; i < 2; i++) {
		writel(original_db76[i], hosts76[i]->ctrl_base + TIMING_DB76);
		put_device(&dsi_devices76[i]->dev);
	}
	drm_bridge_put(dsi_bridge76);
	debugfs_remove_recursive(debug76);
}
