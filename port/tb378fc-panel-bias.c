// SPDX-License-Identifier: GPL-2.0-only
/* TB378FC LCD bias: board-specific because the vendor names the IC only "bias".
 * Register values and GPIO order come from this unit's msm_drm.ko bias_enable().
 * Do not identify it as TPS65132: the vendor writes control register 0x02.
 */
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/regmap.h>
#include <linux/regulator/driver.h>
#include <linux/regulator/of_regulator.h>

struct tb378fc_bias {
	struct regmap *regmap;
	struct gpio_desc *positive;
	struct gpio_desc *negative;
};

static const struct reg_sequence tb378fc_bias_init[] = {
	{ 0x00, 0x13 }, { 0x01, 0x13 }, { 0x02, 0x33 },
};

static int tb378fc_bias_enable(struct regulator_dev *rdev)
{
	struct tb378fc_bias *bias = rdev_get_drvdata(rdev);
	int ret;

	ret = regmap_multi_reg_write(bias->regmap, tb378fc_bias_init,
				     ARRAY_SIZE(tb378fc_bias_init));
	if (ret)
		return ret;
	ret = gpiod_direction_output(bias->positive, 1);
	if (ret)
		return ret;
	/* The vendor repeats the configuration after asserting ENP. */
	ret = regmap_multi_reg_write(bias->regmap, tb378fc_bias_init,
				     ARRAY_SIZE(tb378fc_bias_init));
	if (ret)
		goto fail;
	msleep(5);
	ret = gpiod_direction_output(bias->negative, 1);
	if (!ret)
		return 0;
fail:
	gpiod_direction_output(bias->negative, 0);
	gpiod_direction_output(bias->positive, 0);
	return ret;
}

static int tb378fc_bias_disable(struct regulator_dev *rdev)
{
	struct tb378fc_bias *bias = rdev_get_drvdata(rdev);
	int ret;

	ret = gpiod_direction_output(bias->negative, 0);
	if (ret)
		return ret;
	msleep(5);
	return gpiod_direction_output(bias->positive, 0);
}

static int tb378fc_bias_is_enabled(struct regulator_dev *rdev)
{
	struct tb378fc_bias *bias = rdev_get_drvdata(rdev);
	int pos = gpiod_get_value_cansleep(bias->positive);
	int neg = gpiod_get_value_cansleep(bias->negative);

	if (pos < 0)
		return pos;
	if (neg < 0)
		return neg;
	return pos && neg;
}

static const struct regulator_ops tb378fc_bias_ops = {
	.enable = tb378fc_bias_enable,
	.disable = tb378fc_bias_disable,
	.is_enabled = tb378fc_bias_is_enabled,
};

static const struct regulator_desc tb378fc_bias_desc = {
	.name = "tb378fc-panel-bias",
	.owner = THIS_MODULE,
	.type = REGULATOR_VOLTAGE,
	.ops = &tb378fc_bias_ops,
	/* One logical supply controls the positive and negative rails together.
	 * No voltage programming API: keep the vendor's exact register values.
	 */
};

static const struct regmap_config tb378fc_bias_regmap = {
	.reg_bits = 8,
	.val_bits = 8,
	.max_register = 0x02,
};

static int tb378fc_bias_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct regulator_config config = {};
	struct regulator_dev *rdev;
	struct tb378fc_bias *bias;

	bias = devm_kzalloc(dev, sizeof(*bias), GFP_KERNEL);
	if (!bias)
		return -ENOMEM;
	bias->regmap = devm_regmap_init_i2c(client, &tb378fc_bias_regmap);
	if (IS_ERR(bias->regmap))
		return dev_err_probe(dev, PTR_ERR(bias->regmap), "regmap init failed\n");
	/* Leave inherited rails untouched until the panel requests a transition. */
	bias->positive = devm_gpiod_get(dev, "positive", GPIOD_ASIS);
	if (IS_ERR(bias->positive))
		return dev_err_probe(dev, PTR_ERR(bias->positive), "missing ENP\n");
	bias->negative = devm_gpiod_get(dev, "negative", GPIOD_ASIS);
	if (IS_ERR(bias->negative))
		return dev_err_probe(dev, PTR_ERR(bias->negative), "missing ENN\n");
	config.dev = dev;
	config.of_node = dev->of_node;
	config.driver_data = bias;
	config.init_data = of_get_regulator_init_data(dev, dev->of_node,
						    &tb378fc_bias_desc);
	if (!config.init_data)
		return -EINVAL;
	rdev = devm_regulator_register(dev, &tb378fc_bias_desc, &config);
	return PTR_ERR_OR_ZERO(rdev);
}

static const struct of_device_id tb378fc_bias_match[] = {
	{ .compatible = "lenovo,tb378fc-panel-bias" },
	{ }
};
MODULE_DEVICE_TABLE(of, tb378fc_bias_match);

static struct i2c_driver tb378fc_bias_driver = {
	.probe = tb378fc_bias_probe,
	.driver = {
		.name = "tb378fc-panel-bias",
		.of_match_table = tb378fc_bias_match,
	},
};
module_i2c_driver(tb378fc_bias_driver);
MODULE_DESCRIPTION("Lenovo TB378FC paired LCD bias control");
MODULE_LICENSE("GPL");
