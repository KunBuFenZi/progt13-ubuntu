// SPDX-License-Identifier: GPL-2.0-only
/* Session-resident activation of this board's read-only UFS inspection stack. */
#include <linux/firmware.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>

static struct platform_device *loader;
static int overlay_id;

static int ensure_platform(const char *path)
{
	struct device_node *node, *parent;
	struct platform_device *pdev, *ppdev;
	int ret = 0;

	node = of_find_node_by_path(path);
	if (!node)
		return -ENODEV;
	parent = of_get_parent(node);
	ppdev = of_find_device_by_node(parent);
	of_node_put(parent);
	if (!ppdev) {
		ret = -ENODEV;
		goto out;
	}
	pdev = of_find_device_by_node(node);
	if (pdev) {
		if (pdev->dev.parent != &ppdev->dev)
			ret = -EINVAL;
		platform_device_put(pdev);
	} else if (!of_platform_device_create(node, NULL, &ppdev->dev)) {
		ret = -ENODEV;
	}
	platform_device_put(ppdev);
out:
	of_node_put(node);
	return ret;
}

static int __init live_ufs77_init(void)
{
	const struct firmware *firmware;
	struct device_node *node;
	struct platform_device *pdev;
	const char *paths[] = {
		"/soc@0/rsc@16500000/ufs77-regulators-b",
		"/soc@0/rsc@16500000/ufs77-regulators-d",
		"/soc@0/rsc@16500000/ufs77-regulators-j",
		"/soc@0/phy@1d80000",
		"/soc@0/ufs@1d84000",
	};
	int i, ret;

	node = of_find_compatible_node(NULL, NULL, "lenovo,tb378fc-pmic-glink");
	if (!node)
		return -ENODEV;
	of_node_put(node);
	for (i = 0; i < ARRAY_SIZE(paths); i++) {
		node = of_find_node_by_path(paths[i]);
		if (i < 3) {
			if (node) {
				of_node_put(node);
				return -EBUSY;
			}
			continue;
		}
		if (!node)
			return -ENODEV;
		ret = of_device_is_available(node) ? -EBUSY : 0;
		pdev = of_find_device_by_node(node);
		if (pdev) {
			ret = -EBUSY;
			platform_device_put(pdev);
		}
		of_node_put(node);
		if (ret)
			return ret;
	}
	loader = platform_device_register_simple("tb378fc-ufs77-loader", -1, NULL, 0);
	if (IS_ERR(loader))
		return PTR_ERR(loader);
	ret = request_firmware(&firmware, "tb378fc-ufs77.dtbo", &loader->dev);
	if (ret)
		goto fail;
	ret = of_overlay_fdt_apply(firmware->data, firmware->size, &overlay_id, NULL);
	release_firmware(firmware);
	if (ret) {
		if (overlay_id) {
			int undo = of_overlay_remove(&overlay_id);
			if (undo) {
				pr_err("TB378FC_UFS77 apply=%d remove=%d; retained for inspection\n", ret, undo);
				return 0;
			}
		}
		goto fail;
	}
	for (i = 0; i < ARRAY_SIZE(paths); i++) {
		ret = ensure_platform(paths[i]);
		if (ret)
			pr_err("TB378FC_UFS77 ensure %s=%d; overlay retained\n", paths[i], ret);
	}
	pr_info("TB378FC_UFS77 overlay=%d; session-resident, read-only driver required\n", overlay_id);
	return 0;
fail:
	platform_device_unregister(loader);
	return ret;
}

/* No exit: do not tear down an active HBA or shared power dependencies live. */
module_init(live_ufs77_init);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC session-resident UFS inspection overlay");
