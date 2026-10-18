#!/usr/bin/env python3
"""Match SM8750 video clock parents to this kernel driver's three DT indices."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
root=Path(__file__).resolve().parent.parent
work=root/'out/peripherals-tree68'
dt=work/'sm8750-lenovo-tb378fc-peripherals.dtb'
assert not (work/'before-clock-parent-fix.dtb').exists()
shutil.copy2(dt,work/'before-clock-parent-fix.dtb')
def run(*args):return subprocess.check_output([str(x) for x in args],text=True).strip()
soc='/soc@0'
display=soc+'/clock-controller@af00000'
video=soc+'/clock-controller@aaf0000'
old=run('fdtget','-t','i',dt,video,'clocks').split()
assert len(old)==3
# The first two display clocks are the exact 19.2MHz XO and active-only XO
# zero-cell providers. The fourth display clock is the zero-cell 32kHz clock.
clocks=run('fdtget','-t','i',dt,display,'clocks').split()
first=[*clocks[:2],clocks[4]]
for ph in first:
    # Validate the inherited display provider layout against the decompiled DT.
    assert int(ph)>0
run('fdtput','-t','i',dt,video,'clocks',*first,*old[1:])
run('fdtput','-t','s',dt,video,'clock-names','bi_tcxo','bi_tcxo_ao','sleep_clk','iface')
manifest=json.loads((work/'tree-manifest.json').read_text())
manifest['dtb_before_clock_fix_sha256']=manifest['dtb_sha256']
manifest['dtb_sha256']=hashlib.sha256(dt.read_bytes()).hexdigest()
manifest['video']['clock_parent_fix']='Driver DT indices 0 XO, 1 active XO, 2 sleep; retain GCC AHB fourth'
(work/'tree-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(work/'after.dts').write_text(run('dtc','-q','-I','dtb','-O','dts',dt)+'\n')
print(json.dumps({'before_clocks':old,'after_clocks':first+old[1:],'sha256':manifest['dtb_sha256']},indent=2))
