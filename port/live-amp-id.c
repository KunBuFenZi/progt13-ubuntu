// SPDX-License-Identifier: GPL-2.0-only
/* Removable RAM diagnostic: native amp pins, GPIO I2C, chip ID reads only. */
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/gpio/machine.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_data/i2c-gpio.h>
#include <linux/platform_device.h>

static struct platform_device *bus_device, *reset_device;
static struct gpio_desc *resets[4];
static DEFINE_MUTEX(test_lock);
static int read_id;
static bool ready;
static char result[128] = "NOT_READ";
module_param_string(result, result, sizeof(result), 0444);
MODULE_PARM_DESC(result, "Last real read result, never a substituted chip ID");

static struct gpiod_lookup_table bus_gpios = {
	.dev_id = "i2c-gpio.65",
	.table = {
		GPIO_LOOKUP("f100000.pinctrl", 52, "sda", GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN),
		GPIO_LOOKUP("f100000.pinctrl", 53, "scl", GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN),
		{}
	},
};
static struct gpiod_lookup_table reset_gpios = {
	.dev_id = "tb378fc-live-amp.65",
	.table = {
		GPIO_LOOKUP_IDX("f100000.pinctrl", 106, "reset", 0, GPIO_ACTIVE_LOW),
		GPIO_LOOKUP_IDX("f100000.pinctrl", 128, "reset", 1, GPIO_ACTIVE_LOW),
		GPIO_LOOKUP_IDX("f100000.pinctrl", 120, "reset", 2, GPIO_ACTIVE_LOW),
		GPIO_LOOKUP_IDX("f100000.pinctrl", 108, "reset", 3, GPIO_ACTIVE_LOW),
		{}
	},
};

static int read_native_id(const char *value, const struct kernel_param *parameter)
{
	struct i2c_adapter *adapter;
	u8 address = 0, data[2] = {};
	struct i2c_msg messages[2];
	int index, ret, id = -1;

	if (!ready)
		return -EAGAIN;
	ret = kstrtoint(value, 0, &index);
	if (ret || index < 0 || index > 3)
		return -EINVAL;
	mutex_lock(&test_lock);
	adapter = i2c_get_adapter(65);
	if (!adapter) {
		ret = -ENODEV;
		goto unlock;
	}
	messages[0] = (struct i2c_msg) { .addr = 0x34 + index, .len = 1, .buf = &address };
	messages[1] = (struct i2c_msg) { .addr = 0x34 + index, .flags = I2C_M_RD,
		.len = sizeof(data), .buf = data };
	gpiod_set_value_cansleep(resets[index], 0);
	usleep_range(2000, 3000);
	/* Only selects register 0x00 then reads two bytes; no configuration write. */
	ret = i2c_transfer(adapter, messages, ARRAY_SIZE(messages));
	if (ret == ARRAY_SIZE(messages)) {
		id = (data[0] << 8) | data[1];
		ret = id == 0x2418 ? 0 : -ENODEV;
	} else if (ret >= 0) {
		ret = -EIO;
	}
	gpiod_set_value_cansleep(resets[index], 1);
	i2c_put_adapter(adapter);
	snprintf(result, sizeof(result), "address=0x%02x id=0x%04x error=%d reset=asserted",
		 0x34 + index, id, ret);
	pr_info("TB_LIVE_AMP_ID %s\n", result);
	if (!ret)
		*(int *)parameter->arg = index;
unlock:
	mutex_unlock(&test_lock);
	return ret;
}
static const struct kernel_param_ops read_ops = { .set = read_native_id, .get = param_get_int };
module_param_cb(read_id, &read_ops, &read_id, 0200);
MODULE_PARM_DESC(read_id, "Write index 0..3 to perform one chip ID read then reassert reset");

static void cleanup(void)
{
	int i;
	ready = false;
	if (bus_device) {
		platform_device_unregister(bus_device);
		bus_device = NULL;
	}
	for (i = 0; i < ARRAY_SIZE(resets); i++) {
		if (resets[i]) {
			gpiod_set_value_cansleep(resets[i], 1);
			gpiod_put(resets[i]);
			resets[i] = NULL;
		}
	}
	if (reset_device) {
		platform_device_unregister(reset_device);
		reset_device = NULL;
	}
	gpiod_remove_lookup_table(&reset_gpios);
	gpiod_remove_lookup_table(&bus_gpios);
}

static int __init live_init(void)
{
	struct i2c_gpio_platform_data data = { .udelay = 5 };
	struct device_node *node;
	struct i2c_adapter *adapter;
	int i, ret;

	/* Never contend with an enabled hardware controller on the same lines. */
	node = of_find_node_by_path("/soc@0/geniqup@ac0000/i2c@a94000");
	if (!node)
		return -ENODEV;
	ret = of_device_is_available(node) ? -EBUSY : 0;
	of_node_put(node);
	if (ret)
		return ret;
	gpiod_add_lookup_table(&bus_gpios);
	gpiod_add_lookup_table(&reset_gpios);
	reset_device = platform_device_register_simple("tb378fc-live-amp", 65, NULL, 0);
	if (IS_ERR(reset_device)) {
		ret = PTR_ERR(reset_device);
		reset_device = NULL;
		goto fail;
	}
	for (i = 0; i < ARRAY_SIZE(resets); i++) {
		resets[i] = gpiod_get_index(&reset_device->dev, "reset", i, GPIOD_OUT_HIGH);
		if (IS_ERR(resets[i])) {
			ret = PTR_ERR(resets[i]);
			resets[i] = NULL;
			goto fail;
		}
	}
	bus_device = platform_device_register_data(NULL, "i2c-gpio", 65, &data, sizeof(data));
	if (IS_ERR(bus_device)) {
		ret = PTR_ERR(bus_device);
		bus_device = NULL;
		goto fail;
	}
	adapter = i2c_get_adapter(65);
	if (!adapter) {
		ret = -ENODEV;
		goto fail;
	}
	i2c_put_adapter(adapter);
	ready = true;
	pr_info("TB_LIVE_AMP_READY bus=65 SDA=52 SCL=53, amps reset, no ID read yet\n");
	return 0;
fail:
	cleanup();
	return ret;
}
static void __exit live_exit(void)
{
	cleanup();
	pr_info("TB_LIVE_AMP_REMOVED all amps reset\n");
}
module_init(live_init);
module_exit(live_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC removable GPIO I2C read-only amplifier identity diagnostic");
