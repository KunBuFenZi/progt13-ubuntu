#!/usr/bin/env python3
"""Add the board match and fail closed on unknown touch silicon."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
directory = ROOT / 'kernel/drivers/input/touchscreen/nt36536'
path = directory / 'nt36536.c'
source = path.read_text()
old = '''\tif (!entry) {
		NVT_ERR("chip id not in trim table, continue with NT36536 maps\\n");
		entry = &trim_id_table[0];
	}'''
new = '''\tif (!entry) {
		NVT_ERR("TB378FC_UNKNOWN_TOUCH_ID: refusing firmware download\\n");
		return -ENODEV;
	}'''
if old in source:
    source = source.replace(old, new)
    source = source.replace('''\tAn unmatched id is not fatal here: the id bytes are logged and the
	NT36536 maps are used anyway, so a new trim revision cannot block
	bring-up.''', '''\tAn unmatched id stops probe before firmware download. The board
	port must verify its native memory map before accepting new silicon.''')
else:
    assert 'TB378FC_UNKNOWN_TOUCH_ID' in source
anchor = '\t{ .compatible = "novatek,nt36536-ts", .data = &nt36536_variant },'
if 'lenovo,tb378fc-nvt' not in source:
    assert source.count(anchor) == 1
    source = source.replace(anchor, anchor + '\n\t{ .compatible = "lenovo,tb378fc-nvt", .data = &nt36536_variant },')
path.write_text(source)
source = path.read_text()
if 'static const struct nvt_ts_variant tb378fc_variant' not in source:
    anchor = 'static const struct spi_device_id nvt_ts_id[] = {'
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''/* Native Android input: pen coordinates x10, pressure 0..4095. */
static const struct nvt_ts_variant tb378fc_variant = {
	.pen_coord_scale = 10,
	.pen_pressure_max = 4095,
};

''' + anchor)
    source = source.replace('{ "nt36536-ts", (kernel_ulong_t)&nt36536_variant },',
        '{ "nt36536-ts", (kernel_ulong_t)&nt36536_variant },\n\t{ "tb378fc-nvt", (kernel_ulong_t)&tb378fc_variant },')
    source = source.replace('.compatible = "lenovo,tb378fc-nvt", .data = &nt36536_variant',
                            '.compatible = "lenovo,tb378fc-nvt", .data = &tb378fc_variant')
    path.write_text(source)
path = directory / 'nt36536_mem_map.h'
source = path.read_text()
anchor = '\t{.id = {0xFF, 0xFF, 0xFF, 0x32, 0x65, 0x03},'
if 'TB378FC_NATIVE_TRIM' not in source:
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''\t/* TB378FC_NATIVE_TRIM: the native module also accepts this revision. */
	{.id = {0x15, 0xFF, 0xFF, 0x23, 0x65, 0x03}, .mask = {1, 0, 0, 1, 1, 1},
		.mmap = &NT36536_single_memory_map, .mmap_casc = &NT36536_cascade_memory_map, .hwinfo = &NT36536_hw_info},
''' + anchor)
path.write_text(source)
patch = subprocess.check_output(['git', '-C', str(ROOT / 'kernel'), 'diff', '--',
                                'drivers/input/touchscreen/nt36536'])
(ROOT / 'out/tb378fc-touch.patch').write_bytes(patch)
print('TB378FC_TOUCH_STRICT_IDENTIFICATION_INSTALLED')
