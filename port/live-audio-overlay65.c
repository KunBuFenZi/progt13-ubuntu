// SPDX-License-Identifier: GPL-2.0-only
/* Applies one audited additive overlay from RAM, without replacing the kernel. */
#include <linux/firmware.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

static struct platform_device *device;
static int overlay_id;

static int __init live_overlay_init(void)
{
	const struct firmware *firmware;
	struct device_node *node;
	int ret;

	node = of_find_node_by_path("/soc@0/geniqup@ac0000/i2c@a94000");
	if (!node)
		return -ENODEV;
	ret = of_device_is_available(node) ? -EBUSY : 0;
	of_node_put(node);
	if (ret)
		return ret;
	node = of_find_node_by_path("/soc@0/pinctrl@f100000");
	if (!node)
		return -ENODEV;
	ret = node->phandle == 0x37 ? 0 : -EINVAL;
	of_node_put(node);
	if (ret)
		return ret;
	device = platform_device_register_simple("tb378fc-live-overlay", 65, NULL, 0);
	if (IS_ERR(device))
		return PTR_ERR(device);
	ret = request_firmware(&firmware, "tb378fc-live-audio65.dtbo", &device->dev);
	if (ret)
		goto fail;
	ret = of_overlay_fdt_apply(firmware->data, firmware->size, &overlay_id, NULL);
	release_firmware(firmware);
	if (ret)
		goto fail;
	pr_info("TB_LIVE_AUDIO_OVERLAY id=%d added GPIO I2C and sound; no automatic PCM\n", overlay_id);
	return 0;
fail:
	platform_device_unregister(device);
	return ret;
}

static void __exit live_overlay_exit(void)
{
	int ret = of_overlay_remove(&overlay_id);
	pr_info("TB_LIVE_AUDIO_OVERLAY removed ret=%d\n", ret);
	platform_device_unregister(device);
}

module_init(live_overlay_init);
module_exit(live_overlay_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC audited additive RAM audio overlay loader");
