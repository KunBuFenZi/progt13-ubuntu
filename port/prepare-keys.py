#!/usr/bin/env python3
"""Verify the native button wiring before generating the Lenovo key nodes."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
nodes=json.loads((ROOT/'diagnostics/live-device-tree.json').read_text(encoding='utf-8'))['nodes']
by_path={n['path']:n['props'] for n in nodes}
by_phandle={n['props']['phandle']['cells'][0]:n for n in nodes if 'phandle' in n['props']}
up=by_path['/soc/gpio_keys/vol_up']
assert up['linux,code']['cells']==[115]
phandle,pin,flags=up['gpios']['cells']
assert (pin,flags)==(6,1)
assert by_phandle[phandle]['props']['compatible']['strings']==['qcom,pm8550-gpio']
state=by_phandle[by_path['/soc/gpio_keys']['pinctrl-0']['cells'][0]]['props']
assert state['pins']['strings']==['gpio6'] and state['function']['strings']==['normal']
assert state['power-source']['cells']==[1]
assert 'input-enable' in state and 'bias-pull-up' in state
resin=[n for n in nodes if n['props'].get('compatible',{}).get('strings')==['qcom,pmk8350-resin']]
assert len(resin)==1
assert resin[0]['props']['linux,code']['cells']==[114]
assert resin[0]['props']['interrupts']['cells']==[0,0x13,6,3]

text='''// SPDX-License-Identifier: BSD-3-Clause
/* Volume wiring verified against this TB378FC's native device tree. */
#include "sm8750-lenovo-tb378fc-wifi.dts"

/ {
    gpio-keys {
        compatible = "gpio-keys";
        pinctrl-names = "default";
        pinctrl-0 = <&tb378fc_volume_up>;

        key-volume-up {
            label = "Volume Up";
            linux,code = <KEY_VOLUMEUP>;
            gpios = <&pm8550_gpios 6 GPIO_ACTIVE_LOW>;
            debounce-interval = <15>;
            linux,can-disable;
            wakeup-source;
        };
    };
};

&pm8550_gpios {
    tb378fc_volume_up: volume-up-state {
        pins = "gpio6";
        function = "normal";
        power-source = <1>;
        input-enable;
        bias-pull-up;
    };
};

&pon_resin {
    linux,code = <KEY_VOLUMEDOWN>;
    status = "okay";
};
'''
(ROOT/'port/sm8750-lenovo-tb378fc-keys.dts').write_text(text,encoding='utf-8')
print('NATIVE_VOLUME_KEYS_WIRING_VERIFIED_NOT_YET_HARDWARE_TESTED')
