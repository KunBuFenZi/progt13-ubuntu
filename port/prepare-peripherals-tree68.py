#!/usr/bin/env python3
"""Extend the accepted binary DT only with native Iris and Bluetooth transport."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
work=root/'out/peripherals-tree68';work.mkdir(exist_ok=False)
old=root/'out/native-touch-tree67/sm8750-lenovo-tb378fc-audio-gpio.dtb'
new=work/'sm8750-lenovo-tb378fc-peripherals.dtb'
shutil.copy2(old,new)

def run(*args):
    return subprocess.check_output([str(x) for x in args],text=True).strip()
def nodes(parent='/'):
    yield parent
    for child in run('fdtget','-l',old,parent).splitlines():
        yield from nodes(parent.rstrip('/')+'/'+child)
all_nodes=list(nodes())
def find(compatible):
    hits=[n for n in all_nodes if 'compatible' in run('fdtget','-p',old,n).splitlines()
          and compatible in run('fdtget','-t','s',old,n,'compatible').split()]
    assert len(hits)==1,(compatible,hits)
    return hits[0]
def put(node,prop,kind,*values):
    if values:run('fdtput','-t',kind,new,node,prop,*values)
    else:run('fdtput',new,node,prop)
def phandle(node):
    return int(run('fdtget','-t','i',old,node,'phandle'))

video=find('qcom,sm8750-iris')
assert run('fdtget','-t','s',old,video,'status')=='disabled'
assert run('fdtget','-t','i',old,video,'interrupts')=='0 174 4'
memory=int(run('fdtget','-t','i',old,video,'memory-region'))
reserved=next(n for n in all_nodes if 'phandle' in run('fdtget','-p',old,n).splitlines() and phandle(n)==memory)
assert run('fdtget','-t','x',old,reserved,'reg')=='0 9c300000 0 800000'
put(video,'status','s','okay')
put(video,'firmware-name','s','qcom/sm8750/tb378fc/vpu35_4v.mbn')

# The native Android serial@898000 active pins are gpio24..27, qup2_se6.
uart=next(n for n in all_nodes if n.endswith('/serial@898000'))
assert run('fdtget','-t','s',old,uart,'compatible')=='qcom,geni-uart'
assert run('fdtget','-t','i',old,uart,'interrupts')=='0 461 4'
tlmm=find('qcom,sm8750-tlmm')
data_pins=tlmm+'/qup-uart14-default-state'
flow_pins=tlmm+'/qup-uart14-cts-rts-state'
assert run('fdtget','-t','s',old,data_pins,'pins')=='gpio26 gpio27'
assert run('fdtget','-t','s',old,flow_pins,'pins')=='gpio24 gpio25'
next_phandle=max(phandle(n) for n in all_nodes if 'phandle' in run('fdtget','-p',old,n).splitlines())+1
try: flow_phandle=phandle(flow_pins)
except subprocess.CalledProcessError:
    flow_phandle=next_phandle;put(flow_pins,'phandle','i',flow_phandle);next_phandle+=1
put(uart,'pinctrl-0','i',phandle(data_pins),flow_phandle)
put(uart,'uart-has-rtscts','b')
put(uart,'status','s','okay')
bt=uart+'/bluetooth'
run('fdtput','-c',new,bt)
put(bt,'compatible','s','qcom,wcn7860-bt')
put(bt,'max-speed','i',3200000)
# Use the already validated PMU sequencer, not a second owner of BT_EN.
pmu=find('qcom,wcn7860-pmu')
supplies={'vddrfacmn':'ldo0','vddaon':'ldo1','vddwlcx':'ldo2','vddwlmx':'ldo3',
          'vddrfa0p8':'ldo5','vddrfa1p2':'ldo6','vddrfa1p8':'ldo7'}
for prop,ldo in supplies.items():put(bt,prop+'-supply','i',phandle(pmu+'/regulators/'+ldo))
# Keep the driver's ROM/board-ID selection until controller identification.
# Do not guess a board NVM or use the reference tablet's Bluetooth address.
touch=find('lenovo,tb378fc-nvt')
assert run('fdtget','-t','i',new,touch,'interrupts')=='162 1'
for f,name in [(old,'before.dts'),(new,'after.dts')]:
    (work/name).write_text(subprocess.check_output(['dtc','-q','-I','dtb','-O','dts',str(f)],text=True))
record={'status':'OFFLINE_TREE_NOT_BOOTED','source_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),
        'dtb_sha256':hashlib.sha256(new.read_bytes()).hexdigest(),
        'video':{'node':video,'native_firmware':'vpu35_4v.mbn','reserved':reserved},
        'bluetooth':{'node':bt,'uart_native_address':'0x898000','data_pins':[26,27],'flow_control_pins':[24,25],
                     'firmware_policy':'Identify ROM/board at runtime; native candidates only'},
        'touch_irq':[162,1]}
(work/'tree-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2),flush=True)
