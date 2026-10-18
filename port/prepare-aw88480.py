#!/usr/bin/env python3
"""Install the native-profile codec and board-verified four-amp probe DTS."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
subprocess.run([sys.executable,root/'port/prepare-native-audio.py'],check=True)
source = root/'kernel/sound/soc/codecs'
shutil.copy2(root/'port/aw88480.c',source/'aw88480.c')
kconfig = source/'Kconfig'
text = kconfig.read_text()
entry = '''config SND_SOC_AW88480
	tristate "Awinic AW88480 native-profile amplifier"
	depends on I2C
	select REGMAP_I2C
	select GPIOLIB
	select SND_SOC_AW88395_LIB
	help
	  Support for AW88480 / PID 0x2418 using board-specific ACF register bins.

'''
if 'config SND_SOC_AW88480\n' not in text:
    assert text.count('config SND_SOC_AW88081\n') == 1
    kconfig.write_text(text.replace('config SND_SOC_AW88081\n',entry+'config SND_SOC_AW88081\n'))
makefile = source/'Makefile'
text = makefile.read_text()
if 'CONFIG_SND_SOC_AW88480' not in text:
    makefile.write_text(text+'\nsnd-soc-aw88480-y := aw88480.o\nobj-$(CONFIG_SND_SOC_AW88480) += snd-soc-aw88480.o\n')

nodes = json.loads((root/'diagnostics/live-device-tree.json').read_text())['nodes']
bus = next(n for n in nodes if n['path'].endswith('/i2c@a94000'))
frequency = bus['props'].get('clock-frequency',{}).get('cells',[100000])[0]
assert frequency in (100000,400000)
amps = json.loads((root/'diagnostics/audio-native-config.json').read_text())['native_amplifiers']
assert [(a['address'],a['channel'],a['reset_gpio_specifier'][1]) for a in amps] == [
    (0x34,1,106),(0x35,0,128),(0x36,2,120),(0x37,3,108)]
children = []
for amp in amps:
    address,channel,gpio = amp['address'],amp['channel'],amp['reset_gpio_specifier'][1]
    children.append(f'''
    spk_amp{channel}: amplifier@{address:x} {{
        compatible = "awinic,aw88480";
        reg = <0x{address:x}>;
        #sound-dai-cells = <0>;
        sound-name-prefix = "Amp{channel}";
        awinic,audio-channel = <{channel}>;
        reset-gpios = <&tlmm {gpio} GPIO_ACTIVE_LOW>;
        firmware-name = "awinic/tb378fc/aw88480-native-music.acf";
    }};
''')
dts = '''// SPDX-License-Identifier: BSD-3-Clause
/* Native amp enumeration only: no sound card or automatic playback. */
#include "sm8750-lenovo-tb378fc-battery.dts"

&tlmm {
    tb378fc_amp_resets: amp-resets-state {
        pins = "gpio106", "gpio128", "gpio120", "gpio108";
        function = "gpio";
        drive-strength = <2>;
        bias-disable;
    };
};

&i2c5 {
    status = "okay";
    pinctrl-0 = <&qup_i2c5_data_clk>, <&tb378fc_amp_resets>;
'''+f'    clock-frequency = <{frequency}>;\n'+''.join(children)+'};\n'
(root/'port/sm8750-lenovo-tb378fc-audio-probe.dts').write_text(dts)
shutil.copy2(root/'port/sm8750-lenovo-tb378fc-audio-probe.dts',
             root/'kernel/arch/arm64/boot/dts/qcom/sm8750-lenovo-tb378fc-audio-probe.dts')
print('Four native amps and reset GPIOs verified, I2C frequency',frequency)
