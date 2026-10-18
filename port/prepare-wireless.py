#!/usr/bin/env python3
"""Generate a WCN7860 PCIe bring-up DT after checking native board wiring."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
nodes=json.loads((ROOT/'diagnostics/live-device-tree.json').read_text())['nodes']
cnss=next(n['props'] for n in nodes if n['path']=='/soc/qcom,cnss-peach@b0000000')
assert cnss['wlan-en-gpio']['cells'][1:]==[16,0]
assert cnss['qcom,bt-en-gpio']['cells'][1:]==[3,0]
index={n['props']['phandle']['cells'][0]:n for n in nodes if 'phandle' in n['props']}
expected={'vdd-wlan-io-supply':'regulator-pm-vxf-l3',
          'vdd-wlan-io12-supply':'regulator-pm-vxf-l2',
          'vdd-wlan-aon-supply':'regulator-pm-v8d-s4',
          'vdd-wlan-dig-supply':'regulator-pm-v8f-s5',
          'vdd-wlan-rfa2-supply':'regulator-pm-v8i-s7',
          'vdd-wlan-rfa1-supply':'regulator-pm-v8g-s3'}
for key,suffix in expected.items():
    assert index[cnss[key]['cells'][0]]['path'].endswith('/'+suffix),(key,suffix)
for suffix,pin in [('/pcie0_perst_default/mux','gpio102'),('/pcie0_wake_default/mux','gpio104')]:
    assert next(n['props']['pins']['strings'] for n in nodes if n['path'].endswith(suffix))==[pin]

reference=(ROOT/'reference/sm8750-erhai.dts').read_text()
def block(marker):
    start=reference.index(marker);begin=reference.index('{',start);depth=0
    for i in range(begin,len(reference)):
        if reference[i]=='{':depth+=1
        elif reference[i]=='}':
            depth-=1
            if depth==0:return reference[start:i+2]
    raise AssertionError(marker)

pmu=block('\twcn7860-pmu {')
for old,new in {'wlan_en':'tb378fc_wlan_en','bt_default':'tb378fc_bt_enable',
 'vreg_s7i_1p2':'vreg_s7i','vreg_s3g_1p8':'vreg_s3g'}.items():pmu=pmu.replace(old,new)
pci=block('&pcie0 {')+'\n\n'+block('&pcie0_phy {')+'\n\n'+block('&pcieport0 {')
pci=pci.replace('vreg_l3g_1p2','vreg_l3g')
text='''// SPDX-License-Identifier: BSD-3-Clause
/* TB378FC WCN7860 bring-up: native supply/gpio mapping checked by generator.
 * Firmware/board-data selection and Wi-Fi operation are not yet verified.
 */
#include "sm8750-lenovo-tb378fc-gpu.dts"

/ {
'''+pmu+'''
};

&apps_rsc {
    regulators-d {
        vdd-s4-supply = <&vph_pwr>;
        vreg_s4d_0p85: smps4 {
            regulator-name = "tb378fc-wlan-aon";
            regulator-min-microvolt = <852000>;
            regulator-max-microvolt = <1036000>;
            regulator-initial-mode = <RPMH_REGULATOR_MODE_HPM>;
        };
    };
    regulators-f {
        compatible = "qcom,pm8550ve-rpmh-regulators";
        qcom,pmic-id = "f";
        vdd-l1-supply = <&vreg_s1d>;
        vdd-l2-supply = <&vreg_s7i>;
        vdd-l3-supply = <&vreg_s3g>;
        vdd-s5-supply = <&vph_pwr>;
        vreg_s5f_0p85: smps5 {
            regulator-name = "tb378fc-wlan-dig";
            regulator-min-microvolt = <852000>;
            regulator-max-microvolt = <1000000>;
            regulator-initial-mode = <RPMH_REGULATOR_MODE_HPM>;
        };
        vreg_l1f_0p88: ldo1 {
            regulator-name = "tb378fc-pcie-phy";
            regulator-min-microvolt = <880000>;
            regulator-max-microvolt = <920000>;
            regulator-initial-mode = <RPMH_REGULATOR_MODE_HPM>;
        };
        vreg_l2f_1p2: ldo2 {
            regulator-name = "tb378fc-wlan-io12";
            regulator-min-microvolt = <1200000>;
            regulator-max-microvolt = <1200000>;
            regulator-initial-mode = <RPMH_REGULATOR_MODE_HPM>;
        };
        vreg_l3f_1p8: ldo3 {
            regulator-name = "tb378fc-wlan-io";
            regulator-min-microvolt = <1800000>;
            regulator-max-microvolt = <1800000>;
            regulator-initial-mode = <RPMH_REGULATOR_MODE_HPM>;
        };
    };
};

&tlmm {
    tb378fc_wlan_en: wlan-enable-state {
        pins = "gpio16";
        function = "gpio";
        drive-strength = <16>;
        bias-pull-up;
    };
};

&pm8550ve_f_gpios {
    tb378fc_bt_enable: bt-enable-state {
        pins = "gpio3";
        function = "normal";
        power-source = <1>;
        bias-disable;
        input-disable;
        output-enable;
    };
};

'''+pci+'\n'
(ROOT/'port/sm8750-lenovo-tb378fc-wifi.dts').write_text(text)
print('WIRELESS_DT_NATIVE_WIRING_CHECKED_BUILD_ONLY')
