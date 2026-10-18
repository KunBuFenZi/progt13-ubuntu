#!/usr/bin/env python3
"""Generate a board-specific, RAM-only UFS overlay from the pinned live FDT."""
import argparse
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', default='out/ufs77b')
args = parser.parse_args()
source = root / 'out/ufs77'
work = root / args.output
work.mkdir(exist_ok=False)
nodes = {n['path']: n['props'] for n in json.loads((source / 'mainline-before.json').read_text(encoding='utf-8'))['nodes']}
rsc = '/soc@0/rsc@16500000'
hc = '/soc@0/ufs@1d84000'
phy = '/soc@0/phy@1d80000'
refs = {'/soc@0/pinctrl@f100000': 55, '/vph-pwr-regulator': 285,
        rsc + '/regulators-d/smps1': 288, rsc + '/regulators-i/smps7': 289,
        rsc + '/regulators-g/ldo3': 142, hc: 280, phy: 282}
for path, ph in refs.items():
    assert nodes[path]['phandle']['cells'] == [ph], path
for path in [hc, phy]:
    assert nodes[path]['status']['strings'] == ['disabled']
for provider, rail in [('regulators-b', 'bob2'), ('regulators-b', 'ldo17'), ('regulators-d', 'ldo1'), ('regulators-j', 'ldo1')]:
    assert rsc + '/' + provider + '/' + rail not in nodes
manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
for name in manifest['order']:
    assert hashlib.sha256((source / 'modules' / name).read_bytes()).hexdigest() == manifest['modules'][name]['sha256']

text = '''/dts-v1/;
/plugin/;
/ {
    fragment@0 {
        target-path = "/soc@0/rsc@16500000";
        __overlay__ {
            ufs77-regulators-b {
                compatible = "qcom,pm8550-rpmh-regulators";
                qcom,pmic-id = "b";
                vdd-bob2-supply = <285>;
                vdd-l17-supply = <&ufs77_bob2>;
                ufs77_bob2: bob2 {
                    regulator-name = "vreg_bob2_ufs77";
                    /* Mainline minimum3.0V, within stock2.704..3.008V. */
                    regulator-min-microvolt = <3000000>;
                    regulator-max-microvolt = <3000000>;
                    regulator-initial-mode = <3>;
                };
                ufs77_l17b: ldo17 {
                    regulator-name = "vreg_l17b_ufs77";
                    regulator-min-microvolt = <2504000>;
                    regulator-max-microvolt = <2504000>;
                    regulator-initial-mode = <3>;
                    regulator-allow-set-load;
                    regulator-allowed-modes = <1 3>;
                };
            };
            ufs77-regulators-d {
                compatible = "qcom,pm8550ve-rpmh-regulators";
                qcom,pmic-id = "d";
                vdd-l1-supply = <289>;
                ufs77_l1d: ldo1 {
                    regulator-name = "vreg_l1d_ufs77";
                    regulator-min-microvolt = <1200000>;
                    regulator-max-microvolt = <1200000>;
                    regulator-initial-mode = <3>;
                    regulator-allow-set-load;
                    regulator-allowed-modes = <1 3>;
                };
            };
            ufs77-regulators-j {
                compatible = "qcom,pm8550vs-rpmh-regulators";
                qcom,pmic-id = "j";
                vdd-l1-supply = <288>;
                ufs77_l1j: ldo1 {
                    regulator-name = "vreg_l1j_ufs77";
                    /* Stock PHY requires >=912mV; within its 880..920mV rail. */
                    regulator-min-microvolt = <912000>;
                    regulator-max-microvolt = <912000>;
                    regulator-initial-mode = <3>;
                    regulator-allow-set-load;
                    regulator-allowed-modes = <1 3>;
                };
            };
        };
    };
    fragment@1 {
        target-path = "/soc@0/phy@1d80000";
        __overlay__ {
            vdda-phy-supply = <&ufs77_l1j>;
            vdda-pll-supply = <142>;
            status = "okay";
        };
    };
    fragment@2 {
        target-path = "/soc@0/ufs@1d84000";
        __overlay__ {
            reset-gpios = <55 215 1>;
            vcc-supply = <&ufs77_l17b>;
            vcc-max-microamp = <1300000>;
            vccq-supply = <&ufs77_l1d>;
            vccq-max-microamp = <1200000>;
            status = "okay";
        };
    };
};
'''
(work / 'tb378fc-ufs77.dtso').write_text(text, encoding='utf-8', newline='\n')
record = {'scope': 'read-only RAM UFS discovery; no partitions mounted',
          'build_id': 'f3cebf7974b34aad78e52cb218fccc7e03d13ce7d30f92d0a7a53cf9aec88431',
          'boot_id': '61ec520c-08cc-4e38-a794-2aab6d2f3fea', 'external_phandles': refs,
          'live_initial_fdt_sha256': hashlib.sha256((source / 'mainline-before.dtb').read_bytes()).hexdigest(),
          'dts_sha256': hashlib.sha256(text.encode()).hexdigest(),
          'module_hashes': {n: manifest['modules'][n]['sha256'] for n in manifest['order']},
          'requested_rails': {'bob2_uV': 3000000, 'l17b_uV': 2504000, 'l1d_uV': 1200000, 'l1j_uV': 912000}}
(work / 'overlay-inputs.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': 'OVERLAY_SOURCE_PREPARED', 'dts_sha256': record['dts_sha256']}))
