#!/usr/bin/env python3
"""Create the TB378FC panel driver from the pinned dual-DSI glue and native packets."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
reference = ROOT / 'reference/panel-novatek-nt36536.c'
commands = ROOT / 'diagnostics/nt36526-command-sequence.json'
native = json.loads(commands.read_text())
live_nodes = json.loads((ROOT / 'diagnostics/live-device-tree.json').read_text())['nodes']
timing = next(n for n in live_nodes if n['path'] == native['source_node'])['props']
assert timing['qcom,mdss-dsi-on-command-state']['strings'] == ['dsi_lp_mode']
assert timing['qcom,mdss-dsi-off-command-state']['strings'] == ['dsi_hs_mode']
source = reference.read_text().replace('nt36536', 'nt36526').replace('NT36536', 'NT36526')

def replace(pattern, replacement):
    global source
    source, count = re.subn(pattern, lambda _: replacement, source, flags=re.S)
    assert count == 1, (pattern, count)

tables = '''/* Packet types and delays are preserved, including long writes with
 * two-byte payloads. The standard DCS helper would shorten those packets.
 */
struct tb378fc_panel_cmd {
	u8 type;
	u8 len;
	u16 wait_ms;
	u8 data[17];
};

'''
for kind, description in native['commands'].items():
    rows = []
    reconstructed = b''
    for packet in description['packets']:
        payload = bytes.fromhex(packet['payload'])
        dtype = int(packet['data_type'], 16)
        assert dtype in (0x39, 0x05)
        assert packet['channel'] == 0 and packet['ack'] == 0 and packet['last'] == 1
        assert 0 < len(payload) <= 17
        reconstructed += bytes([dtype, 1, 0, 0, packet['delay_ms']]) + len(payload).to_bytes(2, 'big') + payload
        values = ', '.join(f'0x{x:02x}' for x in payload)
        rows.append(f'\t{{ 0x{dtype:02x}, {len(payload)}, {packet["delay_ms"]}, {{ {values} }} }},')
    assert len(reconstructed) == description['bytes']
    assert hashlib.sha256(reconstructed).hexdigest() == description['sha256']
    tables += f'static const struct tb378fc_panel_cmd tb378fc_{kind}[] = {{\n' + '\n'.join(rows) + '\n};\n\n'

tables += '''static int tb378fc_send_commands(struct novatek_nt36526 *ctx,
		const struct tb378fc_panel_cmd *commands, size_t count, u16 flags)
{
	/* The pinned SM8750 dual-DSI host broadcasts commands from DSI1. */
	struct mipi_dsi_device *dsi = ctx->dsi[1];
	const struct mipi_dsi_host_ops *ops = dsi->host->ops;
	unsigned int i;
	ssize_t ret;

	if (!ops || !ops->transfer)
		return -ENOSYS;
	for (i = 0; i < count; i++) {
		struct mipi_dsi_msg msg = {
			.channel = dsi->channel,
			.type = commands[i].type,
			.tx_buf = commands[i].data,
			.tx_len = commands[i].len,
			.flags = flags,
		};

		ret = ops->transfer(dsi->host, &msg);
		if (ret < 0) {
			dev_err(&dsi->dev, "command %u type %#x failed: %zd\\n",
				i, commands[i].type, ret);
			return ret;
		}
		if (commands[i].wait_ms)
			msleep(commands[i].wait_ms);
	}
	return 0;
}

static int novatek_nt36526_on(struct novatek_nt36526 *ctx)
{
	return tb378fc_send_commands(ctx, tb378fc_on, ARRAY_SIZE(tb378fc_on),
				     MIPI_DSI_MSG_USE_LPM);
}

static int novatek_nt36526_off(struct novatek_nt36526 *ctx)
{
	/* Native off-command-state is HS, unlike the LP on sequence. */
	return tb378fc_send_commands(ctx, tb378fc_off, ARRAY_SIZE(tb378fc_off), 0);
}

'''
replace(r'static int novatek_nt36526_on\(.*?(?=/\*\n \* Supply sequence)', tables)
replace(r'/\*\n \* Supply sequence.*?(?=static int novatek_nt36526_prepare)', '''/* vddio delay from native panel supply entries; bias sequencing is handled
 * by the paired board regulator, using the vendor's ENP/ENN order.
 */
static int novatek_nt36526_power_on(struct novatek_nt36526 *ctx)
{
	int ret;

	ret = regulator_enable(ctx->vddio);
	if (ret)
		return ret;
	msleep(20);
	ret = regulator_enable(ctx->bias);
	if (ret) {
		regulator_disable(ctx->vddio);
		return ret;
	}
	msleep(10);
	return 0;
}

static void novatek_nt36526_power_off(struct novatek_nt36526 *ctx)
{
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	regulator_disable(ctx->bias);
	msleep(5);
	regulator_disable(ctx->vddio);
}

''')
replace(r'static void novatek_nt36526_reset\(.*?\n}', '''static void novatek_nt36526_reset(struct novatek_nt36526 *ctx)
{
	/* Native physical levels: 0/11ms, 1/1ms, 0/3ms, 1/10ms.
	 * The reset descriptor is active-low, so logical 1 asserts reset.
	 */
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	msleep(11);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);
	usleep_range(1000, 1500);
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	usleep_range(3000, 3500);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);
	msleep(10);
}''')
source = source.replace('\tstruct regulator *vsp;\n\tstruct regulator *vsn;', '\tstruct regulator *bias;')
replace(r'\tctx->vsp = devm_regulator_get.*?(?=\tctx->reset_gpio =)', '''\tctx->bias = devm_regulator_get(dev, "bias");
	if (IS_ERR(ctx->bias))
		return dev_err_probe(dev, PTR_ERR(ctx->bias),
				     "failed to get paired bias supply\\n");

''')
replace(r'\t/\*\n\t \* The stock sequence.*?\n\t \*/', '''\t/* The native 0x90/0x91/0x92 commands configure the panel DSC decoder.
	 * Retain those per-link settings; do not send an extra full-width PPS.
	 */''')
replace(r'static const struct drm_display_mode novatek_nt36526_mode.*?(?=static const struct drm_panel_funcs)', '''static const struct drm_display_mode novatek_nt36526_mode = {
	.clock = (1752 + 77 + 16 + 64) * 2 * (2190 + 26 + 4 + 220) * 120 / 1000,
	.hdisplay = 3504,
	.hsync_start = (1752 + 77) * 2,
	.hsync_end = (1752 + 77 + 16) * 2,
	.htotal = (1752 + 77 + 16 + 64) * 2,
	.vdisplay = 2190,
	.vsync_start = 2190 + 26,
	.vsync_end = 2190 + 26 + 4,
	.vtotal = 2190 + 26 + 4 + 220,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int novatek_nt36526_get_modes(struct drm_panel *panel,
				     struct drm_connector *connector)
{
	struct drm_display_mode *mode;

	connector->display_info.width_mm = 280;
	connector->display_info.height_mm = 175;
	connector->display_info.bpc = 10;
	mode = drm_mode_duplicate(connector->dev, &novatek_nt36526_mode);
	if (!mode)
		return -ENOMEM;
	drm_mode_set_name(mode);
	drm_mode_probed_add(connector, mode);
	return 1;
}

''')
source = source.replace('slice_height = 20;', 'slice_height = 30;')
source = source.replace('slice_width = 848;', 'slice_width = 876;')
source = source.replace('1696 / ctx->dsc.slice_width', '1752 / ctx->dsc.slice_width')
source = source.replace('bits_per_component = 8;', 'bits_per_component = 10;')
source = source.replace('MIPI_DSI_FMT_RGB888', 'MIPI_DSI_FMT_RGB101010')
source = source.replace('MIPI_DSI_MODE_VIDEO |\n', 'MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST |\n')
source = source.replace('1696 px', '1752 px').replace('3392', '3504').replace('848-px', '876-px')
source = source.replace('.compatible = "novatek,nt36526"', '.compatible = "lenovo,tb378fc-nt36526"')
source = source.replace(' * Novatek NT36526 dual-DSI video mode panel driver', ' * Lenovo TB378FC / CSOT NT36526 dual-DSI panel driver\n * Board timing and command data extracted from this unit\'s live DT.\n * Common dual-DSI glue from Erwin\'s pinned NT36536 driver.')
source = source.replace('1696', '1752')
source = source.replace('struct mipi_dsi_multi_context dsi_ctx = { .dsi = ctx->dsi[1] };\n', '')
source = source.replace('''\tif (dsi_ctx.accum_err) {
		ret = dsi_ctx.accum_err;
		goto err;
	}

''', '')
source = source.replace('\t\tint ret;', '\tint ret;')
anchor = '\treturn 0;\n\nerr:\n\tnovatek_nt36526_power_off(ctx);'
assert source.count(anchor) == 1
source = source.replace(anchor, '\tdev_info(&ctx->dsi[0]->dev, "TB378FC_PANEL_PREPARED 42 commands complete\\n");\n' + anchor)
destination = ROOT / 'port/panel-novatek-nt36526.c'
destination.write_text(source, newline='\n')
manifest = {'status': 'GENERATED_NOT_HARDWARE_TESTED',
            'reference_commit': '958a2b4654196bb52dfa0217a0f65ffeaa919f81',
            'reference_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
            'packet_source_sha256': hashlib.sha256(commands.read_bytes()).hexdigest(),
            'driver_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
            'on_packets': len(native['commands']['on']['packets']),
            'off_packets': len(native['commands']['off']['packets']),
            'command_states': {'on': 'LP', 'off': 'HS'}}
(ROOT / 'out/nt36526-generation.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
