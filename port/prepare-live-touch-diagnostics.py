#!/usr/bin/env python3
"""Build an isolated, hot-replaceable copy of the matching touch driver.

The default report length and firmware sequence are unchanged. Read-only
aggregate counters distinguish IRQ scheduling, SPI transfers and rejected points.
"""
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent.parent
source = root / 'kernel/drivers/input/touchscreen/nt36536'
dest = root / 'out/live-touch-diagnostics'
dest.mkdir(exist_ok=False)
for item in source.glob('*'):
    if item.suffix in ('.c', '.h'):
        shutil.copy2(item, dest / item.name)

header = dest / 'nt36536.h'
header.write_text(header.read_text().replace('#define NVT_SPI_NAME "nt36536"',
    '#define NVT_SPI_NAME "tb378fc-touch-live"'))
path = dest / 'nt36536.c'
text = path.read_text()

def change(old, new):
    global text
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new)

change('#include <linux/property.h>', '#include <linux/property.h>\n#include <linux/ktime.h>')
extra = r'''
/* No coordinates, raw packets or entered text are exposed. */
static struct {
 u64 hard_irqs, last_hard_ns, threads, spi_ok, spi_error, pm_timeout;
 u64 handshake, watchdog_frames, watchdog_run, watchdog_max_run;
 u64 valid_frames, active_frames, empty_frames, points, out_of_range;
 u64 contacts_begin, contacts_end, sched_max_ns, lock_max_ns;
 u64 spi_max_ns, handler_max_ns, last_done_ns;
 u64 checksum_error;
 u32 previous_mask;
} tb_stats;
static unsigned int tb_report_length = NVT_REPORT_LEN;
static int tb_report_length_set(const char *val, const struct kernel_param *kp)
{
 unsigned int value;
 int ret = kstrtouint(val, 0, &value);
 if (ret)
  return ret;
 if (value != 109 && value != NVT_REPORT_LEN)
  return -EINVAL;
 WRITE_ONCE(*(unsigned int *)kp->arg, value);
 return 0;
}
static const struct kernel_param_ops tb_report_length_ops = {
 .set = tb_report_length_set, .get = param_get_uint,
};
module_param_cb(report_length, &tb_report_length_ops, &tb_report_length, 0644);
MODULE_PARM_DESC(report_length, "IRQ read length: original mainline 121 or native TB378FC 109");

static irqreturn_t tb_touch_hard_irq(int irq, void *data)
{
 WRITE_ONCE(tb_stats.last_hard_ns, ktime_get_ns());
 WRITE_ONCE(tb_stats.hard_irqs, READ_ONCE(tb_stats.hard_irqs) + 1);
 return IRQ_WAKE_THREAD;
}
'''
change('static irqreturn_t nvt_ts_work_func(int irq, void *data)',
       extra + '\nstatic irqreturn_t nvt_ts_work_func(int irq, void *data)')
change('\tuint32_t pen_btn2 = 0;\n\n\tmutex_lock(&ts->lock);', r'''
 uint32_t pen_btn2 = 0;
 u64 thread_ns = ktime_get_ns(), lock_ns, spi_ns, elapsed;
 u64 hard_ns = READ_ONCE(tb_stats.last_hard_ns);
 u32 contact_mask = 0;
 bool watchdog_frame = true;

 mutex_lock(&ts->lock);
 lock_ns = ktime_get_ns();
 tb_stats.threads++;
 if (hard_ns && thread_ns >= hard_ns)
  tb_stats.sched_max_ns = max(tb_stats.sched_max_ns, thread_ns - hard_ns);
 tb_stats.lock_max_ns = max(tb_stats.lock_max_ns, lock_ns - thread_ns);''')
change('\t\t\tNVT_ERR("system(spi) can\'t finished resuming procedure, skip it\\n");',
       '\t\t\ttb_stats.pm_timeout++;\n\t\t\tNVT_ERR("system(spi) can\'t finished resuming procedure, skip it\\n");')
change('\tret = CTP_SPI_READ(ts->client, point_data, NVT_REPORT_LEN);', r'''
 spi_ns = ktime_get_ns();
 ret = CTP_SPI_READ(ts->client, point_data, READ_ONCE(tb_report_length));
 tb_stats.spi_max_ns = max(tb_stats.spi_max_ns, ktime_get_ns() - spi_ns);
 if (ret < 0)
  tb_stats.spi_error++;
 else
  tb_stats.spi_ok++;
 for (i = 1; i <= 6; i++)
  if (point_data[i] != 0xFD && point_data[i] != 0xFE)
   watchdog_frame = false;
 if (ret >= 0 && watchdog_frame) {
  tb_stats.watchdog_frames++;
  tb_stats.watchdog_run++;
  tb_stats.watchdog_max_run = max(tb_stats.watchdog_max_run, tb_stats.watchdog_run);
 } else {
  tb_stats.watchdog_run = 0;
 }''')
change('\tif (nvt_fw_recovery(point_data)) {', '\tif (nvt_fw_recovery(point_data)) {\n\t\ttb_stats.handshake++;')
change('\t\tNVT_ERR("touch report checksum failed:', '\t\ttb_stats.checksum_error++;\n\t\tNVT_ERR("touch report checksum failed:')
change('\tfinger_cnt = 0;\n\n\tfor (i = 0;', '\ttb_stats.valid_frames++;\n\tfinger_cnt = 0;\n\n\tfor (i = 0;')
for condition in [
    '(input_y > ts->abs_y_max * NVT_COORD_SCALE - 1))',
    '(input_y > ts->abs_y_max - 1))']:
    change(condition + '\n\t\t\t\t\tcontinue;', condition + '\n\t\t\t\t{\n\t\t\t\t\ttb_stats.out_of_range++;\n\t\t\t\t\tcontinue;\n\t\t\t\t}')
change('\t\t\tpress_id[input_id - 1] = 1;', '\t\t\tpress_id[input_id - 1] = 1;\n\t\t\tcontact_mask |= BIT(input_id - 1);')
change('\tinput_sync(ts->input_dev);\n\n\tif (ts->pen_support', r'''
 tb_stats.points += finger_cnt;
 if (finger_cnt)
  tb_stats.active_frames++;
 else
  tb_stats.empty_frames++;
 tb_stats.contacts_begin += hweight32(contact_mask & ~tb_stats.previous_mask);
 tb_stats.contacts_end += hweight32(tb_stats.previous_mask & ~contact_mask);
 tb_stats.previous_mask = contact_mask;
 input_sync(ts->input_dev);

 if (ts->pen_support''')
change('XFER_ERROR:\n\n\tmutex_unlock(&ts->lock);', r'''
XFER_ERROR:
 tb_stats.last_done_ns = ktime_get_ns();
 elapsed = tb_stats.last_done_ns - thread_ns;
 tb_stats.handler_max_ns = max(tb_stats.handler_max_ns, elapsed);
 mutex_unlock(&ts->lock);''')
change('request_threaded_irq(client->irq, NULL, nvt_ts_work_func,',
       'request_threaded_irq(client->irq, tb_touch_hard_irq, nvt_ts_work_func,')
stats = r'''
static ssize_t report_stats_show(struct device *dev,
 struct device_attribute *attr, char *buf)
{
 struct nvt_ts_data *core = dev_get_drvdata(dev);
 ssize_t length = 0;
 mutex_lock(&core->lock);
#define TB_STAT(name) length += sysfs_emit_at(buf, length, #name "=%llu\n", (unsigned long long)READ_ONCE(tb_stats.name))
 TB_STAT(hard_irqs); TB_STAT(threads); TB_STAT(spi_ok); TB_STAT(spi_error);
 TB_STAT(pm_timeout); TB_STAT(handshake); TB_STAT(watchdog_frames);
 TB_STAT(watchdog_run); TB_STAT(watchdog_max_run); TB_STAT(checksum_error);
 TB_STAT(valid_frames); TB_STAT(active_frames); TB_STAT(empty_frames);
 TB_STAT(points); TB_STAT(out_of_range); TB_STAT(contacts_begin);
 TB_STAT(contacts_end); TB_STAT(sched_max_ns); TB_STAT(lock_max_ns);
 TB_STAT(spi_max_ns); TB_STAT(handler_max_ns); TB_STAT(last_done_ns);
#undef TB_STAT
 length += sysfs_emit_at(buf, length,
  "awake=%u\npanel_on=%u\npm_suspend=%u\nirq_enabled=%u\nirq_type=%u\nreport_format=%u\nreport_length=%u\nfw_ver=%u\npen_scan=%u\nresume_count=%u\n",
  core->touch_awake, core->panel_on, core->dev_pm_suspend, core->irq_enabled,
  core->int_trigger_type, core->report_format, READ_ONCE(tb_report_length),
  core->fw_ver, core->pen_scan, core->resume_count);
 mutex_unlock(&core->lock);
 return length;
}
static DEVICE_ATTR_RO(report_stats);
'''
change('static struct attribute *nvt_ts_attrs[] = {', stats + '\nstatic struct attribute *nvt_ts_attrs[] = {\n\t&dev_attr_report_stats.attr,')
change('\treturn ts_core && ts_core->pen_input_dev ? attr->mode : 0;',
       '\tif (attr == &dev_attr_report_stats.attr)\n\t\treturn attr->mode;\n\treturn ts_core && ts_core->pen_input_dev ? attr->mode : 0;')
path.write_text(text)
(dest / 'Makefile').write_text('obj-m += tb378fc_touch_live.o\ntb378fc_touch_live-y := nt36536.o nt36536_fw_update.o\n')
(dest / 'source-manifest.json').write_text(json.dumps({
    'scope': 'Aggregate counters; unchanged default protocol; selectable native 109-byte reads',
    'originals': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*') if p.suffix in ('.c', '.h')},
    'generated': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.glob('*') if p.suffix in ('.c', '.h')},
}, indent=2) + '\n')
print(dest)
