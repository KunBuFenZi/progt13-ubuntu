// SPDX-License-Identifier: GPL-2.0-only
/* Exercise the failed lookup without allocating or programming an interrupt. */
#include <linux/irqdomain.h>
#include <linux/module.h>
#include <linux/of.h>

static int __init lookup_init(void)
{
	struct device_node *node;
	struct irq_domain *domain;
	struct irq_fwspec spec = { .param_count = 3, .param = { 0, 0, 4 } };

	node = of_find_compatible_node(NULL, NULL, "lenovo,tb378fc-pmic-glink");
	if (!node)
		return -ENODEV;
	of_node_put(node);
	node = of_find_compatible_node(NULL, NULL, "arm,gic-v3");
	if (!node)
		return -ENODEV;
	spec.fwnode = of_fwnode_handle(node);
	domain = irq_find_matching_fwspec(&spec, DOMAIN_BUS_ANY);
	of_node_put(node);
	if (!domain)
		return -ENODEV;
	pr_info("TB378FC_IRQDOMAIN72 existing GIC domain lookup passed, no IRQ allocated\n");
	return 0;
}
static void __exit lookup_exit(void) { }
module_init(lookup_init);
module_exit(lookup_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Read-only regression probe for the WCD939x IRQ-domain lifetime");
