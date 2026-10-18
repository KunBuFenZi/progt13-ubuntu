// SPDX-License-Identifier: GPL-2.0-only
/* Disable the failed capture link and restore the accepted speaker-only routes. */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/slab.h>

static struct of_changeset recovery;
static const char routes[] = "Speakers\0Amp0 OUT\0Speakers\0Amp1 OUT\0"
			     "Speakers\0Amp2 OUT\0Speakers\0Amp3 OUT";

static struct property *new_property(const char *name, const void *value, size_t size)
{
	struct property *prop = kzalloc(sizeof(*prop), GFP_KERNEL);
	if (!prop)
		return NULL;
	prop->name = kstrdup(name, GFP_KERNEL);
	prop->value = kmemdup(value, size, GFP_KERNEL);
	prop->length = size;
	if (!prop->name || !prop->value)
		return NULL;
	return prop;
}

static int __init recover_init(void)
{
	struct device_node *identity, *sound, *capture;
	struct property *status, *routing;
	int ret;

	identity = of_find_compatible_node(NULL, NULL, "lenovo,tb378fc-pmic-glink");
	if (!identity)
		return -ENODEV;
	of_node_put(identity);
	sound = of_find_node_by_path("/sound");
	capture = of_find_node_by_path("/sound/wcd-capture-dai-link");
	if (!sound || !capture)
		return -ENODEV;
	status = new_property("status", "disabled", sizeof("disabled"));
	routing = new_property("audio-routing", routes, sizeof(routes));
	if (!status || !routing)
		return -ENOMEM;
	of_changeset_init(&recovery);
	ret = of_find_property(capture, "status", NULL) ?
		of_changeset_update_property(&recovery, capture, status) :
		of_changeset_add_property(&recovery, capture, status);
	if (!ret)
		ret = of_changeset_update_property(&recovery, sound, routing);
	if (!ret)
		ret = of_changeset_apply(&recovery);
	of_node_put(capture);
	of_node_put(sound);
	pr_info("TB378FC_RECOVER71 speaker-only device tree restored=%d\n", ret);
	return ret;
}
module_init(recover_init);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Restore speaker-only routes after failed capture hotplug");
