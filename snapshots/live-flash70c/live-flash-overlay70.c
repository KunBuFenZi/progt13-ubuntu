// SPDX-License-Identifier: GPL-2.0-only
/* Apply only this unit's disabled native PM8550 flash node from RAM. */
#include <linux/firmware.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <linux/spmi.h>

static struct platform_device *loader;
static int overlay_id;

static int attach_flash_to_spmi(void)
{
	struct device_node *node, *parent;
	struct platform_device *pdev;
	struct spmi_device *spmi;
	int ret = 0;

	node = of_find_node_by_path("/soc@0/spmi@c400000/pmic@1/led-controller@ee00");
	if (!node)
		return -ENODEV;
	parent = of_get_parent(node);
	spmi = spmi_find_device_by_of_node(parent);
	of_node_put(parent);
	if (!spmi) {
		ret = -ENODEV;
		goto out_node;
	}
	if (!dev_get_regmap(&spmi->dev, NULL)) {
		ret = -ENODEV;
		goto out_parent;
	}
	/* The dynamic OF platform notifier only searches platform-bus parents.
	 * For an SPMI parent it creates an unbound child at the platform root.
	 * Replace only that unbound, just-added flash child with the same OF
	 * device under its actual PMIC; leave every other device untouched.
	 */
	pdev = of_find_device_by_node(node);
	if (pdev) {
		if (pdev->dev.parent == &spmi->dev) {
			platform_device_put(pdev);
			goto out_parent;
		}
		if (pdev->dev.driver) {
			platform_device_put(pdev);
			ret = -EBUSY;
			goto out_parent;
		}
		of_platform_device_destroy(&pdev->dev, NULL);
		platform_device_put(pdev);
	}
	if (!of_platform_device_create(node, NULL, &spmi->dev))
		ret = -ENODEV;
out_parent:
	put_device(&spmi->dev);
out_node:
	of_node_put(node);
	return ret;
}

static int __init live_flash_init(void)
{
	const struct firmware *firmware;
	struct device_node *node;
	u32 base;
	int ret;

	/* ABL preserves the stock QRD root identity. The board-specific PMIC
	 * compatible is retained in the actual Linux tree and is unambiguous.
	 */
	node = of_find_compatible_node(NULL, NULL, "lenovo,tb378fc-pmic-glink");
	if (!node)
		return -ENODEV;
	of_node_put(node);
	node = of_find_node_by_path("/soc@0/spmi@c400000/pmic@1/led-controller@ee00");
	if (!node)
		return -ENODEV;
	ret = of_device_is_available(node) ? -EBUSY : 0;
	if (!ret && !of_device_is_compatible(node, "qcom,pm8550-flash-led"))
		ret = -ENODEV;
	if (!ret && (of_property_read_u32(node, "reg", &base) || base != 0xee00))
		ret = -EINVAL;
	of_node_put(node);
	if (ret)
		return ret;
	loader = platform_device_register_simple("tb378fc-live-flash", 70, NULL, 0);
	if (IS_ERR(loader))
		return PTR_ERR(loader);
	ret = request_firmware(&firmware, "tb378fc-flash70.dtbo", &loader->dev);
	if (ret)
		goto fail;
	ret = of_overlay_fdt_apply(firmware->data, firmware->size, &overlay_id, NULL);
	release_firmware(firmware);
	if (ret)
		goto fail;
	ret = attach_flash_to_spmi();
	if (ret) {
		of_overlay_remove(&overlay_id);
		goto fail;
	}
	pr_info("TB378FC_FLASH70 overlay=%d, default off, torch100mA flash200mA/200ms\n", overlay_id);
	return 0;
fail:
	platform_device_unregister(loader);
	return ret;
}

static void __exit live_flash_exit(void)
{
	int ret = of_overlay_remove(&overlay_id);

	pr_info("TB378FC_FLASH70 overlay removal=%d\n", ret);
	platform_device_unregister(loader);
}

module_init(live_flash_init);
module_exit(live_flash_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC native flash default-off RAM overlay");
