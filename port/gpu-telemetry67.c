// SPDX-License-Identifier: GPL-2.0-only
/* Expose the governor's existing sample. No register reads or power changes. */
#include <linux/devfreq.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/jiffies.h>
#include <linux/kobject.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/sysfs.h>

static struct devfreq *gpu_df;
static struct kobject *telemetry;

static ssize_t sample_show(struct kobject *kobj, struct kobj_attribute *attr,
			   char *buf)
{
	struct devfreq_dev_status sample;
	unsigned long freq;
	bool stopped;
	int suspended;

	mutex_lock(&gpu_df->lock);
	sample = gpu_df->last_status;
	freq = gpu_df->previous_freq;
	stopped = gpu_df->stop_polling;
	suspended = atomic_read(&gpu_df->suspend_count);
	mutex_unlock(&gpu_df->lock);
	return sysfs_emit(buf,
		"busy=%lu\ntotal=%lu\nsample_frequency_hz=%lu\nprevious_frequency_hz=%lu\npolling_stopped=%u\nsuspended=%d\n",
		sample.busy_time, sample.total_time, sample.current_frequency,
		freq, stopped, suspended);
}
static struct kobj_attribute sample_attr = __ATTR_RO(sample);

static int __init telemetry_init(void)
{
	struct device_node *node;
	int ret;

	node = of_find_node_by_path("/soc@0/gpu@3d00000");
	if (!node)
		return -ENODEV;
	gpu_df = devfreq_get_devfreq_by_node(node);
	of_node_put(node);
	if (IS_ERR(gpu_df))
		return PTR_ERR(gpu_df);
	get_device(&gpu_df->dev);
	telemetry = kobject_create_and_add("tb378fc_gpu", kernel_kobj);
	if (!telemetry) {
		put_device(&gpu_df->dev);
		return -ENOMEM;
	}
	ret = sysfs_create_file(telemetry, &sample_attr.attr);
	if (ret) {
		kobject_put(telemetry);
		put_device(&gpu_df->dev);
	}
	return ret;
}
static void __exit telemetry_exit(void)
{
	sysfs_remove_file(telemetry, &sample_attr.attr);
	kobject_put(telemetry);
	put_device(&gpu_df->dev);
}
module_init(telemetry_init);
module_exit(telemetry_exit);
MODULE_DESCRIPTION("TB378FC read-only cached GPU governor telemetry");
MODULE_LICENSE("GPL");
