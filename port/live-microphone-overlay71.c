// SPDX-License-Identifier: GPL-2.0-only
/* Add native codec/SoundWire discovery without touching the working sound card. */
#include <linux/firmware.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

static struct platform_device *loader;
static int overlay_id;

static int __init microphone_overlay_init(void)
{
	const struct firmware *firmware;
	struct device_node *node;
	const char *paths[] = { "/soc@0/soundwire@6ad0000", "/soc@0/soundwire@7630000" };
	int i, ret;

	node = of_find_compatible_node(NULL, NULL, "lenovo,tb378fc-pmic-glink");
	if (!node)
		return -ENODEV;
	of_node_put(node);
	for (i = 0; i < ARRAY_SIZE(paths); i++) {
		node = of_find_node_by_path(paths[i]);
		if (!node)
			return -ENODEV;
		ret = of_device_is_available(node) ? -EBUSY : 0;
		of_node_put(node);
		if (ret)
			return ret;
	}
	node = of_find_node_by_path("/tb378fc-wcd939x");
	if (node) {
		of_node_put(node);
		return -EBUSY;
	}
	loader = platform_device_register_simple("tb378fc-microphone-foundation", 71, NULL, 0);
	if (IS_ERR(loader))
		return PTR_ERR(loader);
	ret = request_firmware(&firmware, "tb378fc-microphone-foundation71.dtbo", &loader->dev);
	if (ret)
		goto fail;
	ret = of_overlay_fdt_apply(firmware->data, firmware->size, &overlay_id, NULL);
	release_firmware(firmware);
	if (ret)
		goto fail;
	pr_info("TB378FC_MIC71 foundation overlay=%d, native1.8V, no capture route\n", overlay_id);
	return 0;
fail:
	platform_device_unregister(loader);
	return ret;
}

static void __exit microphone_overlay_exit(void)
{
	pr_info("TB378FC_MIC71 remove=%d\n", of_overlay_remove(&overlay_id));
	platform_device_unregister(loader);
}

module_init(microphone_overlay_init);
module_exit(microphone_overlay_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC native microphone codec discovery overlay, no capture");
