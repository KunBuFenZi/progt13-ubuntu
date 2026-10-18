// SPDX-License-Identifier: GPL-2.0-only
/*
 * Lenovo TB378FC / CSOT NT36526 dual-DSI panel driver
 * Board timing and command data extracted from this unit's live DT.
 * Common dual-DSI glue from Erwin's pinned NT36536 driver.
 * Copyright (c) 2026, Erwin
 *
 * Dual-DSI handling based on panel-himax-hx83121a.c
 */

#include <linux/backlight.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_graph.h>
#include <linux/regulator/consumer.h>

#include <drm/display/drm_dsc.h>
#include <drm/display/drm_dsc_helper.h>
#include <drm/drm_connector.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>

struct novatek_nt36526 {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi[2];
	struct drm_dsc_config dsc;
	struct gpio_desc *reset_gpio;
	struct regulator *vddio;
	struct regulator *bias;
};

static inline struct novatek_nt36526 *to_novatek_nt36526(struct drm_panel *panel)
{
	return container_of(panel, struct novatek_nt36526, panel);
}

static void novatek_nt36526_reset(struct novatek_nt36526 *ctx)
{
	/* Native physical levels: 0/11ms, 1/1ms, 0/3ms, 1/10ms.
	 * The reset descriptor is active-low, so logical 1 asserts reset.
	 */
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	msleep(11);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);
	usleep_range(1000, 1500);
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	usleep_range(3000, 3500);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);
	msleep(10);
}

/* Packet types and delays are preserved, including long writes with
 * two-byte payloads. The standard DCS helper would shorten those packets.
 */
struct tb378fc_panel_cmd {
	u8 type;
	u8 len;
	u16 wait_ms;
	u8 data[17];
};

static const struct tb378fc_panel_cmd tb378fc_on[] = {
	{ 0x39, 2, 0, { 0xff, 0x20 } },
	{ 0x39, 2, 0, { 0xfb, 0x01 } },
	{ 0x39, 2, 0, { 0x78, 0xd3 } },
	{ 0x39, 2, 0, { 0xff, 0x26 } },
	{ 0x39, 2, 0, { 0xfb, 0x01 } },
	{ 0x39, 2, 0, { 0x93, 0xf4 } },
	{ 0x39, 2, 0, { 0x94, 0xee } },
	{ 0x39, 5, 0, { 0x9a, 0x26, 0x4c, 0x26, 0x26 } },
	{ 0x39, 5, 0, { 0x9b, 0x0f, 0x0f, 0x0f, 0x0f } },
	{ 0x39, 5, 0, { 0x9c, 0xad, 0x2c, 0xad, 0xad } },
	{ 0x39, 5, 0, { 0x9d, 0x10, 0x0f, 0x10, 0x10 } },
	{ 0x39, 5, 0, { 0x9e, 0x19, 0x98, 0x19, 0x19 } },
	{ 0x39, 2, 0, { 0xff, 0x23 } },
	{ 0x39, 2, 0, { 0xfb, 0x01 } },
	{ 0x39, 2, 0, { 0x89, 0xa4 } },
	{ 0x39, 2, 0, { 0xff, 0xe0 } },
	{ 0x39, 2, 0, { 0xfb, 0x01 } },
	{ 0x39, 2, 0, { 0xbb, 0x00 } },
	{ 0x39, 2, 0, { 0xff, 0xf0 } },
	{ 0x39, 2, 0, { 0xfb, 0x01 } },
	{ 0x39, 2, 0, { 0xe6, 0x02 } },
	{ 0x39, 2, 0, { 0xff, 0x27 } },
	{ 0x39, 2, 0, { 0xfb, 0x01 } },
	{ 0x39, 2, 0, { 0xd0, 0x33 } },
	{ 0x39, 2, 0, { 0xd1, 0x05 } },
	{ 0x39, 2, 0, { 0xde, 0x41 } },
	{ 0x39, 2, 0, { 0xdf, 0x00 } },
	{ 0x39, 2, 0, { 0xff, 0x25 } },
	{ 0x39, 2, 0, { 0xfb, 0x01 } },
	{ 0x39, 2, 0, { 0x19, 0x1f } },
	{ 0x39, 2, 0, { 0x1c, 0x10 } },
	{ 0x39, 2, 0, { 0xff, 0x10 } },
	{ 0x39, 2, 0, { 0xfb, 0x01 } },
	{ 0x39, 10, 0, { 0x3b, 0x03, 0xe0, 0x1a, 0x04, 0x04, 0x00, 0x80, 0x36, 0xa1 } },
	{ 0x39, 2, 0, { 0x60, 0x00 } },
	{ 0x39, 3, 0, { 0x90, 0x03, 0x00 } },
	{ 0x39, 17, 0, { 0x91, 0xab, 0xa8, 0x00, 0x1e, 0xd2, 0x00, 0x00, 0x00, 0x03, 0x68, 0x00, 0x0c, 0x03, 0x97, 0x02, 0x17 } },
	{ 0x39, 3, 0, { 0x92, 0x10, 0xf0 } },
	{ 0x39, 3, 0, { 0xb2, 0x91, 0x80 } },
	{ 0x39, 2, 0, { 0xb3, 0x40 } },
	{ 0x05, 1, 120, { 0x11 } },
	{ 0x05, 1, 20, { 0x29 } },
};

static const struct tb378fc_panel_cmd tb378fc_off[] = {
	{ 0x05, 1, 16, { 0x28 } },
	{ 0x05, 1, 120, { 0x10 } },
};

static int tb378fc_send_commands(struct novatek_nt36526 *ctx,
		const struct tb378fc_panel_cmd *commands, size_t count, u16 flags)
{
	/* The pinned SM8750 dual-DSI host broadcasts commands from DSI1. */
	struct mipi_dsi_device *dsi = ctx->dsi[1];
	const struct mipi_dsi_host_ops *ops = dsi->host->ops;
	unsigned int i;
	ssize_t ret;

	if (!ops || !ops->transfer)
		return -ENOSYS;
	for (i = 0; i < count; i++) {
		struct mipi_dsi_msg msg = {
			.channel = dsi->channel,
			.type = commands[i].type,
			.tx_buf = commands[i].data,
			.tx_len = commands[i].len,
			.flags = flags,
		};

		ret = ops->transfer(dsi->host, &msg);
		if (ret < 0) {
			dev_err(&dsi->dev, "command %u type %#x failed: %zd\n",
				i, commands[i].type, ret);
			return ret;
		}
		if (commands[i].wait_ms)
			msleep(commands[i].wait_ms);
	}
	return 0;
}

static int novatek_nt36526_on(struct novatek_nt36526 *ctx)
{
	return tb378fc_send_commands(ctx, tb378fc_on, ARRAY_SIZE(tb378fc_on),
				     MIPI_DSI_MSG_USE_LPM);
}

static int novatek_nt36526_off(struct novatek_nt36526 *ctx)
{
	/* Native off-command-state is HS, unlike the LP on sequence. */
	return tb378fc_send_commands(ctx, tb378fc_off, ARRAY_SIZE(tb378fc_off), 0);
}

/* vddio delay from native panel supply entries; bias sequencing is handled
 * by the paired board regulator, using the vendor's ENP/ENN order.
 */
static int novatek_nt36526_power_on(struct novatek_nt36526 *ctx)
{
	int ret;

	ret = regulator_enable(ctx->vddio);
	if (ret)
		return ret;
	msleep(20);
	ret = regulator_enable(ctx->bias);
	if (ret) {
		regulator_disable(ctx->vddio);
		return ret;
	}
	msleep(10);
	return 0;
}

static void novatek_nt36526_power_off(struct novatek_nt36526 *ctx)
{
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	regulator_disable(ctx->bias);
	msleep(5);
	regulator_disable(ctx->vddio);
}

static int novatek_nt36526_prepare(struct drm_panel *panel)
{
	struct novatek_nt36526 *ctx = to_novatek_nt36526(panel);
	int ret;

	ret = novatek_nt36526_power_on(ctx);
	if (ret < 0)
		return ret;

	novatek_nt36526_reset(ctx);

	/* The native 0x90/0x91/0x92 commands configure the panel DSC decoder.
	 * Retain those per-link settings; do not send an extra full-width PPS.
	 */
	ret = novatek_nt36526_on(ctx);
	if (ret < 0)
		goto err;

	dev_info(&ctx->dsi[0]->dev, "TB378FC_PANEL_PREPARED 42 commands complete\n");
	return 0;

err:
	novatek_nt36526_power_off(ctx);

	return ret;
}

static int novatek_nt36526_unprepare(struct drm_panel *panel)
{
	struct novatek_nt36526 *ctx = to_novatek_nt36526(panel);
	struct device *dev = &ctx->dsi[0]->dev;
	int ret;

	ret = novatek_nt36526_off(ctx);
	if (ret < 0)
		dev_err(dev, "failed to off panel: %d\n", ret);

	novatek_nt36526_power_off(ctx);

	return 0;
}

static const struct drm_display_mode novatek_nt36526_mode = {
	.clock = (1752 + 77 + 16 + 64) * 2 * (2190 + 26 + 4 + 220) * 120 / 1000,
	.hdisplay = 3504,
	.hsync_start = (1752 + 77) * 2,
	.hsync_end = (1752 + 77 + 16) * 2,
	.htotal = (1752 + 77 + 16 + 64) * 2,
	.vdisplay = 2190,
	.vsync_start = 2190 + 26,
	.vsync_end = 2190 + 26 + 4,
	.vtotal = 2190 + 26 + 4 + 220,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int novatek_nt36526_get_modes(struct drm_panel *panel,
				     struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	connector->display_info.width_mm = 280;
	connector->display_info.height_mm = 175;
	connector->display_info.bpc = 10;
	mode = drm_mode_duplicate(connector->dev, &novatek_nt36526_mode);
	if (!mode)
		return -ENOMEM;
	drm_mode_set_name(mode);
	drm_mode_probed_add(connector, mode);
	return 1;
}

static const struct drm_panel_funcs novatek_nt36526_panel_funcs = {
	.prepare = novatek_nt36526_prepare,
	.unprepare = novatek_nt36526_unprepare,
	.get_modes = novatek_nt36526_get_modes,
};

static int novatek_nt36526_probe(struct mipi_dsi_device *dsi)
{
	struct mipi_dsi_device_info dsi_info = { "dsi-secondary", 0, NULL };
	struct mipi_dsi_host *dsi1_host;
	struct device *dev = &dsi->dev;
	struct device_node *dsi1;
	struct novatek_nt36526 *ctx;
	int ret, i;

	ctx = devm_drm_panel_alloc(dev, struct novatek_nt36526, panel,
				   &novatek_nt36526_panel_funcs,
				   DRM_MODE_CONNECTOR_DSI);
	if (IS_ERR(ctx))
		return PTR_ERR(ctx);

	ctx->vddio = devm_regulator_get(dev, "vddio");
	if (IS_ERR(ctx->vddio))
		return dev_err_probe(dev, PTR_ERR(ctx->vddio),
				     "failed to get vddio regulator\n");

	ctx->bias = devm_regulator_get(dev, "bias");
	if (IS_ERR(ctx->bias))
		return dev_err_probe(dev, PTR_ERR(ctx->bias),
				     "failed to get paired bias supply\n");

	ctx->reset_gpio = devm_gpiod_get(dev, "reset", GPIOD_OUT_LOW);
	if (IS_ERR(ctx->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->reset_gpio),
				     "failed to get reset-gpios\n");

	/* port@1 of the panel node points at the secondary DSI host */
	dsi1 = of_graph_get_remote_node(dsi->dev.of_node, 1, -1);
	if (!dsi1)
		return dev_err_probe(dev, -ENODEV,
				     "cannot get secondary DSI node\n");

	dsi1_host = of_find_mipi_dsi_host_by_node(dsi1);
	of_node_put(dsi1);
	if (!dsi1_host)
		return dev_err_probe(dev, -EPROBE_DEFER,
				     "cannot get secondary DSI host\n");

	ctx->dsi[1] = devm_mipi_dsi_device_register_full(dev, dsi1_host,
							 &dsi_info);
	if (IS_ERR(ctx->dsi[1]))
		return dev_err_probe(dev, PTR_ERR(ctx->dsi[1]),
				     "cannot get secondary DSI device\n");

	ctx->dsi[0] = dsi;
	mipi_dsi_set_drvdata(dsi, ctx);
	mipi_dsi_set_drvdata(ctx->dsi[1], ctx);

	ctx->panel.prepare_prev_first = true;

	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret)
		return dev_err_probe(dev, ret, "failed to get backlight\n");

	drm_panel_add(&ctx->panel);

	/* This panel only supports DSC; unconditionally enable it */
	ctx->dsc.dsc_version_major = 1;
	ctx->dsc.dsc_version_minor = 2;
	ctx->dsc.slice_height = 30;
	ctx->dsc.slice_width = 876;
	ctx->dsc.slice_count = 1752 / ctx->dsc.slice_width;
	ctx->dsc.bits_per_component = 10;
	ctx->dsc.bits_per_pixel = 8 << 4; /* 4 fractional bits */
	ctx->dsc.block_pred_enable = true;

	for (i = 0; i < 2; i++) {
		ctx->dsi[i]->lanes = 4;
		ctx->dsi[i]->format = MIPI_DSI_FMT_RGB101010;
		/* Vendor stock keeps the DSI clock lane in continuous HS (no
		 * NON_CONTINUOUS property in the panel dtsi); this DSC video
		 * panel loses receiver lock if the clock lane drops to LP
		 * during blanking, so match the vendor and run continuous. */
		ctx->dsi[i]->mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST |
					  MIPI_DSI_MODE_LPM;
		ctx->dsi[i]->dsc = &ctx->dsc;
		/* vendor packs two 876-px slices into each video packet */
		ctx->dsi[i]->dsc_slice_per_pkt = 2;

		ret = devm_mipi_dsi_attach(dev, ctx->dsi[i]);
		if (ret < 0) {
			drm_panel_remove(&ctx->panel);
			return dev_err_probe(dev, ret,
					     "failed to attach to DSI host\n");
		}
	}

	return 0;
}

static void novatek_nt36526_remove(struct mipi_dsi_device *dsi)
{
	struct novatek_nt36526 *ctx = mipi_dsi_get_drvdata(dsi);

	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id novatek_nt36526_of_match[] = {
	{ .compatible = "lenovo,tb378fc-nt36526" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, novatek_nt36526_of_match);

static struct mipi_dsi_driver novatek_nt36526_driver = {
	.probe = novatek_nt36526_probe,
	.remove = novatek_nt36526_remove,
	.driver = {
		.name = "panel-novatek-nt36526",
		.of_match_table = novatek_nt36526_of_match,
	},
};
module_mipi_dsi_driver(novatek_nt36526_driver);

MODULE_AUTHOR("Erwin <yzddmr7@gmail.com>");
MODULE_DESCRIPTION("Novatek NT36526 dual-DSI video mode panel driver");
MODULE_LICENSE("GPL");
