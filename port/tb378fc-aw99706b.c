// SPDX-License-Identifier: GPL-2.0-only
/* TB378FC AW99706B: preserve the board's vendor register configuration.
 * Source: aw99706b_init_table and _bl_set_brightness in this unit's msm_drm.ko.
 * No MTP writes and no guessed current limits.
 */
#include <linux/backlight.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/regmap.h>

struct tb378fc_bl {
	struct regmap *regmap;
	struct regmap *secondary;
	struct gpio_desc *enable;
	struct mutex lock;
	bool on;
};

static int tb378fc_bl_write(struct tb378fc_bl *ctx, unsigned int reg,
			   unsigned int value)
{
	int ret = regmap_write(ctx->regmap, reg, value);

	if (!ret)
		ret = regmap_write(ctx->secondary, reg, value);
	return ret;
}

static const struct reg_sequence tb378fc_bl_init[] = {
	{ 0x0d, 0x00 }, { 0x0c, 0x48 }, { 0x06, 0xd9 }, { 0x07, 0x05 },
	{ 0x04, 0x00 }, { 0x05, 0x00 }, { 0x08, 0x01 }, { 0x0d, 0xfe },
};

static int tb378fc_bl_update(struct backlight_device *bl)
{
	struct tb378fc_bl *ctx = bl_get_data(bl);
	unsigned int brightness = backlight_get_brightness(bl);
	int ret = 0;

	mutex_lock(&ctx->lock);
	if (!brightness) {
		if (ctx->on)
			ret = tb378fc_bl_write(ctx, 0x0d, 0x00);
		gpiod_direction_output(ctx->enable, 0);
		ctx->on = false;
		goto out;
	}
	if (!ctx->on) {
		ret = gpiod_direction_output(ctx->enable, 1);
		if (ret)
			goto out;
		usleep_range(5000, 6000);
		ret = regmap_multi_reg_write(ctx->regmap, tb378fc_bl_init,
					    ARRAY_SIZE(tb378fc_bl_init));
		if (ret)
			goto disable;
		ret = regmap_multi_reg_write(ctx->secondary, tb378fc_bl_init,
					    ARRAY_SIZE(tb378fc_bl_init));
		if (ret)
			goto disable;
		ctx->on = true;
	}
	ret = tb378fc_bl_write(ctx, 0x04, (brightness >> 8) & 0x0f);
	if (ret)
		goto disable;
	ret = tb378fc_bl_write(ctx, 0x05, brightness & 0xff);
	if (!ret)
		goto out;
disable:
	gpiod_direction_output(ctx->enable, 0);
	ctx->on = false;
out:
	mutex_unlock(&ctx->lock);
	return ret;
}

static const struct backlight_ops tb378fc_bl_ops = {
	.options = BL_CORE_SUSPENDRESUME,
	.update_status = tb378fc_bl_update,
};

static const struct regmap_config tb378fc_bl_regmap = {
	.reg_bits = 8,
	.val_bits = 8,
	/* Registers 0x1e/0x1f control MTP. Keep them inaccessible. */
	.max_register = 0x13,
};

static int tb378fc_bl_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct backlight_properties props = {
		.type = BACKLIGHT_RAW,
		.max_brightness = 4095,
		.brightness = 906,
		.power = BACKLIGHT_POWER_OFF,
	};
	struct backlight_device *bl;
	struct tb378fc_bl *ctx;
	struct device_node *secondary_bus;
	struct i2c_adapter *adapter;
	struct i2c_client *secondary;
	unsigned int id;
	int ret;

	ctx = devm_kzalloc(dev, sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return -ENOMEM;
	mutex_init(&ctx->lock);
	ctx->regmap = devm_regmap_init_i2c(client, &tb378fc_bl_regmap);
	if (IS_ERR(ctx->regmap))
		return dev_err_probe(dev, PTR_ERR(ctx->regmap), "regmap init failed\n");
	/* Native DT: primary 888000:76, secondary 880000:76; shared HWEN. */
	secondary_bus = of_parse_phandle(dev->of_node, "lenovo,secondary-i2c-bus", 0);
	if (!secondary_bus)
		return dev_err_probe(dev, -EINVAL, "missing secondary backlight bus\n");
	adapter = of_find_i2c_adapter_by_node(secondary_bus);
	of_node_put(secondary_bus);
	if (!adapter)
		return dev_err_probe(dev, -EPROBE_DEFER, "secondary bus not ready\n");
	secondary = devm_i2c_new_dummy_device(dev, adapter, 0x76);
	i2c_put_adapter(adapter);
	if (IS_ERR(secondary))
		return dev_err_probe(dev, PTR_ERR(secondary), "secondary client failed\n");
	ctx->secondary = devm_regmap_init_i2c(secondary, &tb378fc_bl_regmap);
	if (IS_ERR(ctx->secondary))
		return dev_err_probe(dev, PTR_ERR(ctx->secondary), "secondary regmap failed\n");
	ctx->enable = devm_gpiod_get(dev, "enable", GPIOD_ASIS);
	if (IS_ERR(ctx->enable))
		return dev_err_probe(dev, PTR_ERR(ctx->enable), "missing HWEN\n");
	/* UEFI has already enabled HWEN. Reading ID does not alter its setup. */
	ret = regmap_read(ctx->regmap, 0x11, &id);
	if (ret)
		return dev_err_probe(dev, ret, "chip ID read failed\n");
	if (id != 0x07)
		return dev_err_probe(dev, -ENODEV, "unexpected chip ID %02x\n", id);
	ret = regmap_read(ctx->secondary, 0x11, &id);
	if (ret)
		return dev_err_probe(dev, ret, "secondary chip ID read failed\n");
	if (id != 0x07)
		return dev_err_probe(dev, -ENODEV, "unexpected secondary ID %02x\n", id);
	dev_info(dev, "TB378FC_DUAL_BACKLIGHT both chip IDs verified\n");
	bl = devm_backlight_device_register(dev, "tb378fc-backlight", dev,
					   ctx, &tb378fc_bl_ops, &props);
	return PTR_ERR_OR_ZERO(bl);
}

static const struct of_device_id tb378fc_bl_match[] = {
	{ .compatible = "lenovo,tb378fc-aw99706b" },
	{ }
};
MODULE_DEVICE_TABLE(of, tb378fc_bl_match);

static struct i2c_driver tb378fc_bl_driver = {
	.probe = tb378fc_bl_probe,
	.driver = {
		.name = "tb378fc-aw99706b",
		.of_match_table = tb378fc_bl_match,
	},
};
module_i2c_driver(tb378fc_bl_driver);
MODULE_DESCRIPTION("Lenovo TB378FC AW99706B backlight");
MODULE_LICENSE("GPL");
