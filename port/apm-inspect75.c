// SPDX-License-Identifier: GPL-2.0
/* Read-only snapshots of the current APM state. No callback or DSP changes. */
#include <linux/debugfs.h>
#include <linux/device.h>
#include <linux/idr.h>
#include <linux/module.h>
#include <linux/seq_file.h>
#include <linux/soc/qcom/apr.h>
#include "q6apm.h"

/* Exact prefix from this build's drivers/soc/qcom/apr.c. */
struct router_prefix75 {
	struct rpmsg_endpoint *ch;
	struct device *dev;
	spinlock_t svcs_lock;
	spinlock_t rx_lock;
	struct idr svcs_idr;
	int dest_domain_id, type;
};
struct stream75 {
	u32 port, id, shm, opcode, status, periods, pending, hw;
	u32 bytes, map;
	u64 phys;
};
static struct dentry *directory;

static int inspect_show(struct seq_file *s, void *unused)
{
	struct device *dev = bus_find_device_by_name(&aprbus, NULL, "gprsvc:service:2:1");
	struct audioreach_graph *ar;
	struct audioreach_sub_graph *sg;
	struct audioreach_container *container;
	struct audioreach_module *mod;
	struct router_prefix75 *router;
	struct pkt_router_svc *svc;
	struct stream75 streams[16] = {};
	struct q6apm *apm;
	unsigned long flags;
	int id, n = 0, i;

	if (!dev)
		return -ENODEV;
	apm = dev_get_drvdata(dev);
	if (!apm || apm->dev != dev || !apm->gdev) {
		put_device(dev);
		return -ENODEV;
	}
	seq_printf(s, "apm_state=%u result=%#x/%u\n", READ_ONCE(apm->state),
		   READ_ONCE(apm->result.opcode), READ_ONCE(apm->result.status));
	mutex_lock(&apm->lock);
	idr_for_each_entry(&apm->graph_idr, ar, id) {
		struct audioreach_graph_info *info = ar->info;
		seq_printf(s, "graph=%d starts=%d refs=%u map=%#x src=%#x:%u dst=%#x:%u\n",
			   id, ar->start_count, kref_read(&ar->refcount), info->mem_map_handle,
			   info->src_mod_inst_id, info->src_mod_op_port_id,
			   info->dst_mod_inst_id, info->dst_mod_ip_port_id);
		list_for_each_entry(sg, &info->sg_list, node) {
			seq_printf(s, " sg=%#x direction=%u perf=%u scenario=%u\n",
				   sg->sub_graph_id, sg->direction, sg->perf_mode, sg->scenario_id);
			list_for_each_entry(container, &sg->container_list, node) {
				seq_printf(s, "  container=%#x cap=%#x domain=%u position=%u\n",
					   container->container_id, container->capability_id,
					   container->proc_domain, container->graph_pos);
				list_for_each_entry(mod, &container->modules_list, node) {
					seq_printf(s, "   iid=%#x mid=%#x interface=%u/%u links=%u",
						   mod->instance_id, mod->module_id, mod->hw_interface_type,
						   mod->hw_interface_idx, mod->num_connections);
					for (i = 0; i < min_t(u32, mod->num_connections, AR_MAX_MOD_LINKS); i++)
						seq_printf(s, " %u->%#x:%u", mod->src_mod_op_port_id[i],
							   mod->dst_mod_inst_id[i], mod->dst_mod_ip_port_id[i]);
					seq_putc(s, '\n');
				}
			}
		}
	}
	mutex_unlock(&apm->lock);
	router = (void *)apm->gdev->svc.pr;
	spin_lock_irqsave(&router->svcs_lock, flags);
	idr_for_each_entry(&router->svcs_idr, svc, id) {
		struct q6apm_graph *g;
		struct stream75 *out;
		if (id < 0x10000000 || !svc->dev || svc->dev->parent != dev || !svc->priv)
			continue;
		g = svc->priv;
		if (g->apm != apm || g->port != svc || n == ARRAY_SIZE(streams))
			continue;
		out = &streams[n++];
		out->port = id;
		out->id = g->id;
		out->shm = g->shm_iid;
		out->opcode = READ_ONCE(g->result.opcode);
		out->status = READ_ONCE(g->result.status);
		out->periods = READ_ONCE(g->tx_data.num_periods);
		out->pending = READ_ONCE(g->tx_data.dsp_buf);
		out->hw = atomic_read(&g->tx_data.hw_ptr);
		out->map = g->info->mem_map_handle;
		/* Buffer fields change under graph->lock: do not dereference them here. */
	}
	spin_unlock_irqrestore(&router->svcs_lock, flags);
	for (i = 0; i < n; i++) {
		struct stream75 *p = &streams[i];
		seq_printf(s, "stream port=%#x graph=%u shm=%#x result=%#x/%u periods=%u next=%u hw=%u map=%#x\n",
			   p->port, p->id, p->shm, p->opcode, p->status,
			   p->periods, p->pending, p->hw, p->map);
	}
	put_device(dev);
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(inspect);
static int __init inspect_init(void)
{
	directory = debugfs_create_dir("tb378fc-apm75", NULL);
	if (IS_ERR(directory))
		return PTR_ERR(directory);
	debugfs_create_file("state", 0400, directory, NULL, &inspect_fops);
	return 0;
}
static void __exit inspect_exit(void) { debugfs_remove_recursive(directory); }
module_init(inspect_init);
module_exit(inspect_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TB378FC read-only APM graph snapshot");
