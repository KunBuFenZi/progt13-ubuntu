#!/usr/bin/env python3
"""Build isolated camera modules against the running kernel ABI, without loading."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume', action='store_true')
args = parser.parse_args()
kernel = root / 'kernel'
reference = root / 'reference/camera74/h0cheung-kernel'
work = root / 'out/camera74'
work.mkdir(exist_ok=args.resume)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
verified = json.loads((reference / 'source-verified.json').read_text())
assert verified['commit'] == 'bf96c3d4048973298ede78487177c6f1b4f6bc0f'
assert not any('error' in x for x in verified['files'])
for item in verified['files']:
    assert sha(reference / item['path']) == item['sha256'], item['path']
assert sha(reference / 'drivers/media/i2c/gc08a8.c') == json.loads((reference / 'gc08a8-api-source.json').read_text())['sha256']

sdk = root / 'out/module-camera-sdk74'
sdk.mkdir(exist_ok=args.resume)
base_sdk = root / 'out/module-microphone-sdk71'
shutil.copy2(base_sdk / '.config', sdk / '.config')
subprocess.run([str(kernel / 'scripts/config'), '--file', str(sdk / '.config'),
                '-m', 'VIDEO_GC08A3', '-e', 'V4L_PLATFORM_DRIVERS',
                '-m', 'VIDEO_QCOM_CAMSS', '-m', 'VIDEO_OV13B10'], check=True)
env = dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-')
subprocess.run(['make', '-C', str(kernel), 'O=' + str(sdk), 'LOCALVERSION=+',
                'olddefconfig', 'prepare', 'modules_prepare', '-j2'], env=env, check=True)
shutil.copy2(root / 'out/kernel-usbc70b/vmlinux.symvers', sdk / 'Module.symvers')

def config(path):
    return {line.split('=')[0]: line.split('=', 1)[1] for line in Path(path).read_text().splitlines() if line.startswith('CONFIG_')}

before = config(base_sdk / '.config'); after = config(sdk / '.config')
changed = {key: [before.get(key), after.get(key)] for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
allowed = {'CONFIG_V4L2_CCI_I2C', 'CONFIG_V4L2_CCI', 'CONFIG_VIDEO_GC08A3', 'CONFIG_V4L_PLATFORM_DRIVERS',
           'CONFIG_VIDEO_QCOM_CAMSS', 'CONFIG_VIDEO_OV13B10', 'CONFIG_VIDEOBUF2_DMA_SG'}
assert not changed.keys() - allowed, changed
assert after['CONFIG_V4L2_CCI_I2C'] == after['CONFIG_VIDEO_QCOM_CAMSS'] == 'm'
assert (sdk / 'include/generated/utsrelease.h').read_text().strip() == '#define UTS_RELEASE "7.2.0-tb378fc-wifi+"'

source_manifest = {}
for directory in ['core', 'sensor', 'cci', 'clocks', 'camss']:
    (work / directory).mkdir(exist_ok=args.resume)

def copy(source, dest):
    shutil.copy2(source, dest)
    source_manifest[str(dest.relative_to(work))] = {'source': str(source.relative_to(root)), 'sha256': sha(source)}

for source in (reference / 'drivers/media/platform/qcom/camss').iterdir():
    if source.suffix in ['.c', '.h'] or source.name == 'Makefile':
        copy(source, work / 'camss' / source.name)
(work / 'camss/Makefile').write_text((work / 'camss/Makefile').read_text().replace('obj-$(CONFIG_VIDEO_QCOM_CAMSS)', 'obj-m'))

for source in ['v4l2-cci.c', 'v4l2-async.c', 'v4l2-fwnode.c']:
    copy(kernel / 'drivers/media/v4l2-core' / source, work / 'core' / source)
for source in (kernel / 'drivers/media/v4l2-core').glob('*.h'):
    copy(source, work / 'core' / source.name)
copy(kernel / 'drivers/media/common/videobuf2/videobuf2-dma-sg.c', work / 'core/videobuf2-dma-sg.c')
(work / 'core/Makefile').write_text('obj-m += v4l2-cci.o v4l2-async.o v4l2-fwnode.o videobuf2-dma-sg.o\n')

copy(kernel / 'drivers/i2c/busses/i2c-qcom-cci.c', work / 'cci/i2c-qcom-cci.c')
(work / 'cci/Makefile').write_text('obj-m += i2c-qcom-cci.o\n')
for header in (kernel / 'drivers/clk/qcom').glob('*.h'):
    copy(header, work / 'clocks' / header.name)
for name in ['camcc-sm8750.c', 'cambistmclkcc-sm8750.c']:
    assert sha(kernel / 'drivers/clk/qcom' / name) == sha(reference / 'drivers/clk/qcom' / name)
    copy(kernel / 'drivers/clk/qcom' / name, work / 'clocks' / name)
(work / 'clocks/Makefile').write_text('obj-m += camcc-sm8750.o cambistmclkcc-sm8750.o\n')

patches = []
for name, origin in [('gc08a8.c', reference / 'drivers/media/i2c/gc08a8.c'),
                     ('ov13b10.c', kernel / 'drivers/media/i2c/ov13b10.c')]:
    text = original = origin.read_text()
    if name == 'gc08a8.c':
        old = '\tret = gc08a8_init_controls(sensor);'
        assert text.count(old) == 1
        text = text.replace(old, '\tdev_info(dev, "GC08A8 identity confirmed: %#llx\\n", id);\n\n' + old)
    else:
        old = '#include <linux/module.h>'
        assert text.count(old) == 1
        text = text.replace(old, old + '\n#include <linux/of.h>')
        old = '\tstruct gpio_desc *reset;'
        assert text.count(old) == 1
        text = text.replace(old, old + '\n\tbool tb378fc;\n\tstruct regulator *vaf;')
        old = 'static int ov13b10_power_off(struct device *dev)'
        assert text.count(old) == 1
        text = text.replace(old, '''/* Native TB378FC sequence decoded from its camera module binary.
 * Parent supplies and voltage constraints are represented in device tree.
 */
static int ov13b10_tb378fc_power_on(struct ov13b10 *sensor)
{
\tconst unsigned int order[] = { 1, 0, 2 }; /* AVDD, DOVDD, DVDD */
\tint ret, i;

\tgpiod_set_value_cansleep(sensor->reset, 1);
\tfsleep(1000);
\tret = regulator_enable(sensor->vaf);
\tif (ret)
\t\treturn ret;
\tfsleep(5000);
\tfor (i = 0; i < ARRAY_SIZE(order); i++) {
\t\tret = regulator_enable(sensor->supplies[order[i]].consumer);
\t\tif (ret)
\t\t\tgoto disable;
\t}
\tgpiod_set_value_cansleep(sensor->reset, 0);
\tfsleep(5000);
\tret = clk_prepare_enable(sensor->img_clk);
\tif (ret)
\t\tgoto disable;
\tfsleep(1000);
\treturn 0;

disable:
\tgpiod_set_value_cansleep(sensor->reset, 1);
\twhile (i--)
\t\tregulator_disable(sensor->supplies[order[i]].consumer);
\tregulator_disable(sensor->vaf);
\treturn ret;
}

static int ov13b10_tb378fc_power_off(struct ov13b10 *sensor)
{
\tregulator_disable(sensor->vaf);
\tfsleep(5000);
\tgpiod_set_value_cansleep(sensor->reset, 1);
\tfsleep(1000);
\tclk_disable_unprepare(sensor->img_clk);
\tfsleep(1000);
\tregulator_disable(sensor->supplies[2].consumer);
\tregulator_disable(sensor->supplies[0].consumer);
\tregulator_disable(sensor->supplies[1].consumer);
\treturn 0;
}

''' + old)
        old = '''\tstruct ov13b10 *ov13b10 = to_ov13b10(sd);

\tgpiod_set_value_cansleep(ov13b10->reset, 1);'''
        assert text.count(old) == 1
        text = text.replace(old, '''\tstruct ov13b10 *ov13b10 = to_ov13b10(sd);

\tif (ov13b10->tb378fc)
\t\treturn ov13b10_tb378fc_power_off(ov13b10);

\tgpiod_set_value_cansleep(ov13b10->reset, 1);''')
        old = '''\tret = clk_prepare_enable(ov13b10->img_clk);'''
        assert text.count(old) == 1
        text = text.replace(old, '''\tif (ov13b10->tb378fc)
\t\treturn ov13b10_tb378fc_power_on(ov13b10);

''' + old)
        old = '''\tov13b->dev = &client->dev;'''
        assert text.count(old) == 1
        text = text.replace(old, old + '''
\tov13b->tb378fc = of_device_is_compatible(client->dev.of_node,
\t\t\t\t\t       "lenovo,tb378fc-ov13b10");
\tif (ov13b->tb378fc) {
\t\tov13b->vaf = devm_regulator_get(ov13b->dev, "vaf");
\t\tif (IS_ERR(ov13b->vaf))
\t\t\treturn dev_err_probe(ov13b->dev, PTR_ERR(ov13b->vaf),
\t\t\t\t\t     "failed to get native VAF rail\\n");
\t}''')
        old = '"reset",\n\t\t\t\t\t       GPIOD_OUT_LOW);'
        assert text.count(old) == 1
        text = text.replace(old, '"reset",\n\t\t\t\t\t       GPIOD_OUT_HIGH);')
        old = 'static struct i2c_driver ov13b10_i2c_driver = {'
        assert text.count(old) == 1
        text = text.replace(old, 'static const struct of_device_id ov13b10_of_match[] = {\n\t{ .compatible = "ovti,ov13b10" },\n\t{}\n};\nMODULE_DEVICE_TABLE(of, ov13b10_of_match);\n\n' + old)
        old = '\t\t.name = "ov13b10",'
        assert text.count(old) == 1
        text = text.replace(old, old + '\n\t\t.of_match_table = ov13b10_of_match,')
    (work / 'sensor' / name).write_text(text)
    source_manifest['sensor/' + name] = {'source': str(origin.relative_to(root)), 'before_sha256': sha(origin),
                                         'after_sha256': sha(work / 'sensor' / name)}
    patches.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile='a/' + name, tofile='b/' + name))
(work / 'sensor-adjustments.patch').write_text(''.join(patches))
(work / 'sensor/Makefile').write_text('obj-m += gc08a8.o ov13b10.o\n')
(work / 'Makefile').write_text('obj-m += core/ cci/ clocks/ sensor/ camss/\n')
extra = work / 'extra.symvers'
extra.write_text(''.join(line for line in (root / 'out/media-closure68b/Module.symvers').read_text().splitlines(True)
                         if Path(line.split()[2]).name not in ['v4l2-async', 'v4l2-fwnode', 'v4l2-cci', 'videobuf2-dma-sg']))
subprocess.run(['make', '-C', str(kernel), 'O=' + str(sdk), 'LOCALVERSION=+',
                'M=' + str(work), 'clean'], env=env, check=True)
subprocess.run(['make', '-C', str(kernel), 'O=' + str(sdk), 'LOCALVERSION=+', '-j3',
                'M=' + str(work), 'KBUILD_EXTRA_SYMBOLS=' + str(extra),
                'modules'], env=env, check=True)
modules = {}
exports = {line.split()[1] for path in [sdk / 'Module.symvers', root / 'out/media-closure68b/Module.symvers']
           for line in path.read_text().splitlines()}
for p in sorted(work.rglob('*.ko')):
    names = subprocess.check_output(['aarch64-linux-gnu-nm', str(p)], text=True)
    undefined = subprocess.check_output(['aarch64-linux-gnu-nm', '-u', str(p)], text=True)
    magic = subprocess.check_output(['modinfo', '-F', 'vermagic', str(p)], text=True).strip()
    assert magic == '7.2.0-tb378fc-wifi+ SMP preempt mod_unload aarch64'
    entry = {'sha256': sha(p), 'vermagic': magic,
             'exports': [s.split()[-1].removeprefix('__ksymtab_') for s in names.splitlines() if s.split() and s.split()[-1].startswith('__ksymtab_')],
             'imports': [s.split()[-1] for s in undefined.splitlines() if s.split()]}
    modules[str(p.relative_to(work))] = entry
    exports.update(entry['exports'])
missing = {name: sorted(set(item['imports']) - exports) for name, item in modules.items() if set(item['imports']) - exports}
assert not missing, missing
assert len(modules) == 10, list(modules)
manifest = {'status': 'CAMERA74_MODULES_BUILT_NOT_LOADED', 'kernel_image_unchanged': True,
            'reference_kernel_commit': verified['commit'], 'build_sdk_config_changes': changed,
            'sources': source_manifest, 'modules': modules, 'camera_stream_started': False,
            'microphone_stream_started': False, 'remaining': ['Native DT validation', 'Live export closure', 'Sensor identity', 'Camera capture and desktop integration']}
(work / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'status': manifest['status'], 'modules': list(modules), 'config_changes': changed}, indent=2))
