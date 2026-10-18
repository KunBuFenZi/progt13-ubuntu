// SPDX-License-Identifier: GPL-2.0-only
/* Correct only the failed, unused UFS BOB2 provider's constraints in RAM. */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include "bob77-overlay.h"

static int overlay_id;

static int __init ufs_bob77_init(void)
{
	struct device_node *node, *parent;
	struct platform_device *pdev;
	u32 lo, hi;
	int ret;

	node = of_find_node_by_path("/soc@0/rsc@16500000/ufs77-regulators-b/bob2");
	if (!node)
		return -ENODEV;
	parent = of_get_parent(node);
	pdev = of_find_device_by_node(parent);
	of_node_put(parent);
	if (!pdev || pdev->dev.driver) {
		ret = -EBUSY;
		goto out;
	}
	ret = of_property_read_u32(node, "regulator-min-microvolt", &lo);
	if (ret)
		goto out;
	ret = of_property_read_u32(node, "regulator-max-microvolt", &hi);
	if (ret)
		goto out;
	if (lo != 2720000 || hi != 2720000) {
		ret = -EINVAL;
		goto out;
	}
	ret = of_overlay_fdt_apply(bob77_overlay, sizeof(bob77_overlay), &overlay_id, NULL);
	if (!ret)
		pr_info("TB378FC_UFS77 BOB2 request3.0V inside stock2.704..3.008V; awaiting probe\n");
out:
	platform_device_put(pdev);
	of_node_put(node);
	return ret;
}

module_init(ufs_bob77_init);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC unused UFS BOB2 constraint correction");
