#!/usr/bin/env python3
"""Build TB378FC's native split ADC SoundWire map on the verified IRQ fix."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
work = root / 'out/microphone73'
work.mkdir(exist_ok=False)
base = root / 'out/microphone72'
codec = work / 'codec'
codec.mkdir()
source = (base / 'codec/wcd939x-sdw.c').read_text()
text = source
anchor = 'static struct sdw_dpn_prop wcd939x_rx_dpn_prop[WCD939X_MAX_RX_SWR_PORTS] = {'
table_start = source.index('static const struct wcd_sdw_ch_info wcd939x_sdw_tx_ch_info[] = {')
table_end = source.index('\n};', table_start) + 3
table = source[table_start:table_end].replace('wcd939x_sdw_tx_ch_info[]', 'tb378fc_native_tx_ch_info[]')
for adc, bit in [(3, 0), (4, 1)]:
    old = f'WCD_SDW_CH(WCD939X_ADC{adc}, WCD939X_ADC_1_4_PORT, BIT({adc - 1}))'
    new = f'WCD_SDW_CH(WCD939X_ADC{adc}, WCD939X_ADC_DMIC_1_2_PORT, BIT({bit}))'
    assert table.count(old) == 1
    table = table.replace(old, new)
addition = '''/* Lenovo's stock qcom,tx_swr_ch_map separates ADC1/2 on DP1
 * from ADC3/4 on DP2. Stock's slave port indices are zero based.
 * Keep the generic map for every other machine.
 */
''' + table + '''

static bool wcd939x_is_tb378fc(void)
{
\tstruct device_node *node;
\tbool found;

\tnode = of_find_compatible_node(NULL, NULL, "lenovo,tb378fc-pmic-glink");
\tfound = !!node;
\tof_node_put(node);

\treturn found;
}

'''
assert text.count(anchor) == 1
text = text.replace(anchor, addition + anchor)
anchor = '\t\twcd->ch_info = &wcd939x_sdw_tx_ch_info[0];'
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + '''
\t\tif (wcd939x_is_tb378fc()) {
\t\t\t/* Native SWRM_TX2_CH1 -> master DP3 -> SWR_MIC4,
\t\t\t * and SWRM_TX3_CH1 -> master DP4 -> SWR_MIC8.
\t\t\t * Also normalize the old trial DT for online replacement.
\t\t\t */
\t\t\tpdev->m_port_map[1] = 3;
\t\t\tpdev->m_port_map[2] = 4;
\t\t\tpdev->m_port_map[3] = 3;
\t\t\tpdev->m_port_map[4] = 4;
\t\t\twcd->ch_info = tb378fc_native_tx_ch_info;
\t\t\tdev_info(dev, "TB378FC native ADC map: DP1/ch1->DP3/ch1, DP2/ch1->DP4/ch1\\n");
\t\t}''')
for header in (base / 'codec').glob('*.h'):
    shutil.copy2(header, codec / header.name)
(codec / 'wcd939x-sdw.c').write_text(text)
(codec / 'Makefile').write_text('obj-m += snd-soc-wcd939x-sdw.o\nsnd-soc-wcd939x-sdw-y := wcd939x-sdw.o\n')
patch = ''.join(difflib.unified_diff(source.splitlines(True), text.splitlines(True),
                                  fromfile='a/sound/soc/codecs/wcd939x-sdw.c',
                                  tofile='b/sound/soc/codecs/wcd939x-sdw.c'))
(work / 'wcd939x-native-adc-map.patch').write_text(patch)
subprocess.run(['make', '-C', str(root / 'kernel'),
                'O=' + str(root / 'out/module-microphone-sdk71'), 'LOCALVERSION=+', '-j2',
                'M=' + str(codec), 'KBUILD_EXTRA_SYMBOLS=' + str(base / 'extra.symvers'), 'modules'],
               check=True, env=dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-'))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest = json.loads((base / 'manifest.json').read_text())
manifest['status'] = 'NATIVE_ADC_MAP73_BUILT_NOT_LOADED'
manifest['native_source_commit'] = '4838bbc2e0cd21f353ee8c5bda628f6b24295fb4'
manifest['native_map_patch_sha256'] = sha(work / 'wcd939x-native-adc-map.patch')
manifest['base72_sdw_source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
manifest['sources']['wcd939x-sdw.c']['after_sha256'] = sha(codec / 'wcd939x-sdw.c')
manifest['native_routes'] = {'ADC1': {'slave_port': 1, 'slave_channel_mask': 1, 'master_port': 3, 'swr_mic': 4},
                             'ADC3': {'slave_port': 2, 'slave_channel_mask': 1, 'master_port': 4, 'swr_mic': 8}}
manifest['capture_opened'] = False
modules = work / 'modules'
modules.mkdir()
for name, entry in manifest['modules'].items():
    origin = codec / name if name == 'snd-soc-wcd939x-sdw.ko' else base / 'modules' / name
    if origin.parent != codec:
        assert sha(origin) == entry['sha256']
    dest = modules / name
    shutil.copy2(origin, dest)
    entry['sha256'] = sha(dest)
    assert subprocess.check_output(['modinfo', '-F', 'vermagic', str(dest)], text=True).strip() == entry['vermagic']
    entry['imports'] = [line.split()[-1] for line in subprocess.check_output(['aarch64-linux-gnu-nm', '-u', str(dest)], text=True).splitlines()]
    entry['exports'] = [line.split()[-1].removeprefix('__ksymtab_') for line in subprocess.check_output(['aarch64-linux-gnu-nm', str(dest)], text=True).splitlines()
                        if line.split() and line.split()[-1].startswith('__ksymtab_')]
(work / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'status': manifest['status'], 'sdw_sha256': manifest['modules']['snd-soc-wcd939x-sdw.ko']['sha256'],
                  'native_routes': manifest['native_routes']}, indent=2))
