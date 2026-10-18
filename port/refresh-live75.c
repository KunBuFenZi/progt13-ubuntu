// SPDX-License-Identifier: GPL-2.0-only
/* RAM-only get_modes extension. Never rebind or power-cycle the live panel. */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <drm/drm_device.h>
#include <drm/drm_drv.h>
#include <drm/drm_connector.h>
#include <drm/drm_panel.h>
#include <drm/drm_modes.h>
#include <drm/drm_modeset_lock.h>
#include <drm/drm_probe_helper.h>
#include "msm_drv.h"

static struct drm_panel *tablet_panel;
static struct drm_device *tablet_drm;
static const struct drm_panel_funcs *original_funcs;
static struct drm_panel_funcs extended_funcs;

#include "refresh-hooks75.h"

static void tablet_reprobe(void)
{
    struct drm_connector *connector;
    struct drm_connector_list_iter iter;

    mutex_lock(&tablet_drm->mode_config.mutex);
    drm_connector_list_iter_begin(tablet_drm, &iter);
    drm_for_each_connector_iter(connector, &iter) {
        if (connector->connector_type == DRM_MODE_CONNECTOR_DSI &&
            connector->funcs && connector->funcs->fill_modes)
            connector->funcs->fill_modes(connector,
                tablet_drm->mode_config.max_width, tablet_drm->mode_config.max_height);
    }
    drm_connector_list_iter_end(&iter);
    mutex_unlock(&tablet_drm->mode_config.mutex);
    drm_kms_helper_hotplug_event(tablet_drm);
}

/* Native live Android DT, shared with the independently compiled kernel. */
static const struct drm_display_mode extra_modes[] = {
    {
        .clock = 1117910,
        .hdisplay = 3504, .hsync_start = 3658, .hsync_end = 3690, .htotal = 3818,
        .vdisplay = 2190, .vsync_start = 4656, .vsync_end = 4660, .vtotal = 4880,
        .type = DRM_MODE_TYPE_DRIVER,
    },
    {
        .clock = 1205533,
        .hdisplay = 3504, .hsync_start = 3624, .hsync_end = 3656, .htotal = 3688,
        .vdisplay = 2190, .vsync_start = 2216, .vsync_end = 2220, .vtotal = 2270,
        .type = DRM_MODE_TYPE_DRIVER,
    },
};

static int tablet_get_modes(struct drm_panel *panel, struct drm_connector *connector)
{
    struct drm_display_mode *mode;
    int count, i;

    lockdep_assert_held(&connector->dev->mode_config.mutex);
    count = original_funcs->get_modes(panel, connector);
    if (panel != tablet_panel || count != 1)
        return count;
    for (i = 0; i < ARRAY_SIZE(extra_modes); i++) {
        mode = drm_mode_duplicate(connector->dev, &extra_modes[i]);
        if (!mode)
            break;
        drm_mode_set_name(mode);
        drm_mode_probed_add(connector, mode);
        count++;
    }
    return count;
}

static int __init tablet_refresh_init(void)
{
    struct platform_device *pdev;
    struct msm_drm_private *priv;
    struct device_node *np;
    struct drm_connector *connector;
    struct drm_connector_list_iter iter;
    struct drm_display_mode *mode;
    bool valid = false;
    int ret = -ENODEV;

    np = of_find_node_by_path("/soc@0/display-subsystem@ae00000/display-controller@ae01000");
    if (!np)
        return -ENODEV;
    pdev = of_find_device_by_node(np);
    of_node_put(np);
    if (!pdev)
        return -ENODEV;
    priv = platform_get_drvdata(pdev);
    if (priv && priv->dev) {
        tablet_drm = priv->dev;
        drm_dev_get(tablet_drm);
    }
    put_device(&pdev->dev);
    if (!tablet_drm)
        return -ENODEV;
    np = of_find_node_by_path("/soc@0/display-subsystem@ae00000/dsi@ae94000/panel@0");
    if (!np)
        goto put_drm;
    tablet_panel = of_drm_find_panel(np);
    of_node_put(np);
    if (IS_ERR(tablet_panel)) {
        ret = PTR_ERR(tablet_panel);
        goto put_drm;
    }
    drm_panel_get(tablet_panel);
    drm_modeset_lock_all(tablet_drm);
    drm_connector_list_iter_begin(tablet_drm, &iter);
    drm_for_each_connector_iter(connector, &iter) {
        if (connector->connector_type != DRM_MODE_CONNECTOR_DSI)
            continue;
        list_for_each_entry(mode, &connector->modes, head) {
            if (mode->hdisplay == 3504 && mode->vdisplay == 2190 &&
                mode->clock == 1117910 && mode->htotal == 3818 &&
                mode->vtotal == 2440 && drm_mode_vrefresh(mode) == 120)
                valid = true;
        }
    }
    drm_connector_list_iter_end(&iter);
    original_funcs = tablet_panel->funcs;
    if (!valid || !original_funcs || !original_funcs->get_modes) {
        drm_modeset_unlock_all(tablet_drm);
        drm_panel_put(tablet_panel);
        goto put_drm;
    }
    ret = install_hooks75();
    if (ret) {
        drm_modeset_unlock_all(tablet_drm);
        drm_panel_put(tablet_panel);
        goto put_drm;
    }
    extended_funcs = *original_funcs;
    extended_funcs.get_modes = tablet_get_modes;
    WRITE_ONCE(tablet_panel->funcs, &extended_funcs);
    drm_modeset_unlock_all(tablet_drm);
    tablet_reprobe();
    pr_info("TB378FC_REFRESH75_READY native 60/120/144; current mode not changed; unarmed\n");
    return 0;
put_drm:
    drm_dev_put(tablet_drm);
    tablet_drm = NULL;
    return ret;
}

static void __exit tablet_refresh_exit(void)
{
    drm_modeset_lock_all(tablet_drm);
    remove_hooks75();
    WRITE_ONCE(tablet_panel->funcs, original_funcs);
    drm_modeset_unlock_all(tablet_drm);
    tablet_reprobe();
    drm_panel_put(tablet_panel);
    drm_dev_put(tablet_drm);
}
module_init(tablet_refresh_init);
module_exit(tablet_refresh_exit);
MODULE_DESCRIPTION("TB378FC native refresh mode enumeration, RAM-only live test");
MODULE_LICENSE("GPL");
