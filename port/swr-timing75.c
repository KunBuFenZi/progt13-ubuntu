// SPDX-License-Identifier: GPL-2.0
/* RAM-only board timing trial. Change idle software configuration, no MMIO. */
#include <linux/module.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/soundwire/sdw.h>
#include <linux/mutex.h>
#include <linux/completion.h>

/* Exact prefix from the running soundwire-qcom build's qcom.c. */
struct port75 {
	u16 si;
	u8 off1, off2, bp_mode, hstart, hstop, word_length, blk_group_count, lane_control;
};
struct ctrl75 {
	struct sdw_bus bus;
	struct device *dev;
	struct regmap *regmap;
	u32 max_reg;
	const unsigned int *reg_layout;
	void __iomem *mmio;
	struct reset_control *audio_cgcr;
#ifdef CONFIG_DEBUG_FS
	struct dentry *debugfs;
#endif
	struct completion broadcast, enumeration;
	struct mutex port_lock;
	struct clk *hclk;
	int irq;
	unsigned int version;
	int wake_irq, num_din_ports, num_dout_ports, nports, cols_index, rows_index;
	unsigned long port_mask;
	u32 intr_mask;
	u8 rcmd_id, wcmd_id;
	struct port75 *pconfig;
};
static struct ctrl75 *ctrl;
static struct device *device;
static struct module *driver_owner;
static struct port75 saved[2];
static int __init timing_init(void)
{
	struct device_node *np;
	struct platform_device *pdev;
	int ret = -ENODEV;
	np = of_find_node_by_path("/soc@0/soundwire@7630000");
	if (!np)
		return ret;
	pdev = of_find_device_by_node(np);
	of_node_put(np);
	if (!pdev)
		return ret;
	device = &pdev->dev;
	ctrl = dev_get_drvdata(device);
	if (!ctrl || ctrl->dev != device || !ctrl->bus.dev || ctrl->bus.dev->parent != device ||
	    ctrl->num_din_ports != 4 || ctrl->num_dout_ports != 0 || ctrl->nports != 4 ||
	    !ctrl->pconfig || !device->driver)
		goto fail;
	driver_owner = device->driver->owner;
	if (!try_module_get(driver_owner))
		goto fail;
	mutex_lock(&ctrl->bus.bus_lock);
	mutex_lock(&ctrl->port_lock);
	if ((ctrl->port_mask & ~1UL) || !list_empty(&ctrl->bus.m_rt_list)) {
		ret = -EBUSY;
		goto unlock;
	}
	if (ctrl->pconfig[3].si != 3 || ctrl->pconfig[4].si != 3 ||
	    ctrl->pconfig[3].off1 != 1 || ctrl->pconfig[4].off1 != 1 ||
	    ctrl->bus.params.curr_dr_freq != 19200000) {
		pr_info("TB378FC_SWR75 original DP3=%u/%u/%u DP4=%u/%u/%u rate=%u\n",
			ctrl->pconfig[3].si, ctrl->pconfig[3].off1, ctrl->pconfig[3].lane_control,
			ctrl->pconfig[4].si, ctrl->pconfig[4].off1, ctrl->pconfig[4].lane_control,
			ctrl->bus.params.curr_dr_freq);
		ret = -EINVAL;
		goto unlock;
	}
	saved[0] = ctrl->pconfig[3];
	saved[1] = ctrl->pconfig[4];
	/* Native ADC_LP is 4.8 MHz; the bus data rate is 19.2 MHz.
	 * Stock UC0 sends ADC1 on lane1/offset0, ADC3 on lane0/offset2. */
	ctrl->pconfig[3].off1 = 0;
	ctrl->pconfig[3].lane_control = 1;
	ctrl->pconfig[4].off1 = 2;
	ctrl->pconfig[4].lane_control = 0;
	ret = 0;
	pr_info("TB378FC_SWR75 idle timings: ADC1 DP3 lane1/off0, ADC3 DP4 lane0/off2, interval4\n");
unlock:
	mutex_unlock(&ctrl->port_lock);
	mutex_unlock(&ctrl->bus.bus_lock);
	if (!ret)
		return 0;
	module_put(driver_owner);
fail:
	put_device(device);
	return ret;
}
static void __exit timing_exit(void)
{
	mutex_lock(&ctrl->bus.bus_lock);
	mutex_lock(&ctrl->port_lock);
	ctrl->pconfig[3] = saved[0];
	ctrl->pconfig[4] = saved[1];
	mutex_unlock(&ctrl->port_lock);
	mutex_unlock(&ctrl->bus.bus_lock);
	module_put(driver_owner);
	put_device(device);
}
module_init(timing_init);
module_exit(timing_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC native ADC LP transport timing trial");
