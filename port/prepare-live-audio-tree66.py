#!/usr/bin/env python3
"""Keep the native four-amp routing, using the live-verified GPIO I2C pins."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
probe = (root/'port/sm8750-lenovo-tb378fc-audio-probe.dts').read_text()
audio = (root/'port/sm8750-lenovo-tb378fc-audio.dts').read_text()
old = '''&i2c5 {
    status = "okay";
    pinctrl-0 = <&qup_i2c5_data_clk>, <&tb378fc_amp_resets>;
    clock-frequency = <100000>;'''
new = '''/* Never let the hardware GPI controller claim these same lines. */
&i2c5 { status = "disabled"; };

&tlmm {
    tb378fc_gpio_i2c: tb378fc-amp-i2c-state {
        pins = "gpio52", "gpio53";
        function = "gpio";
        drive-strength = <2>;
        bias-pull-up;
    };
};

/ {
    tb378fc_amp_bus: tb378fc-amp-i2c {
    compatible = "i2c-gpio";
    #address-cells = <1>;
    #size-cells = <0>;
    sda-gpios = <&tlmm 52 (GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN)>;
    scl-gpios = <&tlmm 53 (GPIO_ACTIVE_HIGH | GPIO_OPEN_DRAIN)>;
    i2c-gpio,delay-us = <5>;
    pinctrl-names = "default";
    pinctrl-0 = <&tb378fc_gpio_i2c>, <&tb378fc_amp_resets>;'''
assert probe.count(old) == 1
probe = probe.replace(old,new)
assert probe.endswith('};\n')
probe += '};\n'
assert audio.count('#include "sm8750-lenovo-tb378fc-audio-probe.dts"') == 1
audio = audio.replace('#include "sm8750-lenovo-tb378fc-audio-probe.dts"', '')
result = probe+'\n'+audio
dest = root/'port/sm8750-lenovo-tb378fc-audio-gpio.dts'
dest.write_text(result)
print(dest)
