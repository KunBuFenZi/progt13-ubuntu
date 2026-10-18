// SPDX-License-Identifier: GPL-2.0-only
/* Add capture card links. Userspace unbinds/rebinds only the sound card. */
#include <linux/firmware.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

static struct platform_device *loader;
static int overlay_id;

static int __init capture_init(void)
{
	const struct firmware *firmware;
	struct device_node *node;
	int ret;

	node = of_find_compatible_node(NULL, NULL, "lenovo,tb378fc-pmic-glink");
	if (!node)
		return -ENODEV;
	of_node_put(node);
	node = of_find_node_by_path("/tb378fc-wcd939x");
	if (!node)
		return -ENODEV;
	of_node_put(node);
	node = of_find_node_by_path("/sound/wcd-capture-dai-link");
	if (node) {
		of_node_put(node);
		return -EBUSY;
	}
	loader = platform_device_register_simple("tb378fc-microphone-capture", 71, NULL, 0);
	if (IS_ERR(loader))
		return PTR_ERR(loader);
	ret = request_firmware(&firmware, "tb378fc-microphone-capture71.dtbo", &loader->dev);
	if (ret)
		goto fail;
	ret = of_overlay_fdt_apply(firmware->data, firmware->size, &overlay_id, NULL);
	release_firmware(firmware);
	if (ret)
		goto fail;
	pr_info("TB378FC_MIC71 capture links overlay=%d, no stream opened\n", overlay_id);
	return 0;
fail:
	platform_device_unregister(loader);
	return ret;
}

static void __exit capture_exit(void)
{
	pr_info("TB378FC_MIC71 capture links remove=%d\n", of_overlay_remove(&overlay_id));
	platform_device_unregister(loader);
}
module_init(capture_init);
module_exit(capture_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC microphone capture DAI links, no recording");
