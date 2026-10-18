#!/usr/bin/env python3
"""Build an isolated UART adapter for the currently unbound native BT port."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
root=Path(__file__).resolve().parent.parent
sdk=root/'out/kernel-peripherals68'
source=root/'kernel/drivers/tty/serial/qcom_geni_serial.c'
work=root/'out/bt-uart-live68b';work.mkdir(exist_ok=False)
text=source.read_text()
# No serial alias exists in the accepted ABL DT. The upstream allocator passes
# -ENODEV + 1 as an unsigned lower bound and fails before touching the hardware.
old='ida_alloc_range(&port_ida, max_alias_num + 1,'
assert text.count(old)==1
text=text.replace(old,'ida_alloc_range(&port_ida, max(max_alias_num, -1) + 1,')
text=text.replace('#if IS_ENABLED(CONFIG_SERIAL_QCOM_GENI_CONSOLE)','#if 0 /* Console belongs to the original built-in driver. */')
text=text.replace('.driver_name = "qcom_geni_uart"','.driver_name = "tb378fc_geni_uart_tty"')
text=text.replace('.dev_name = "ttyHS"','.dev_name = "ttyTBBT"')
text=text.replace('.name = "qcom_geni_serial"','.name = "tb378fc_geni_uart"')
assert text.count('ret = console_register(&qcom_geni_console_driver);')==1
text=text.replace('ret = console_register(&qcom_geni_console_driver);','ret = 0; /* The built-in console remains the sole console owner. */')
text=text.replace('console_unregister(&qcom_geni_console_driver);','(void)0; /* No console was registered by this module. */')
old='data = of_device_get_match_data(&pdev->dev);'
assert text.count(old)==1
text=text.replace(old,'if (strcmp(dev_name(&pdev->dev), "898000.serial"))\n\t\treturn -ENODEV;\n\n\t'+old)
path=work/'tb378fc_geni_uart.c';path.write_text(text)
(work/'Makefile').write_text('obj-m += tb378fc_geni_uart.o\n')
shutil.copy2(sdk/'vmlinux.symvers',sdk/'Module.symvers')
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
subprocess.run(['make','-C',str(root/'kernel'),'O='+str(sdk),'LOCALVERSION=+','-j3','M='+str(work),'modules'],env=env,check=True)
p=work/'tb378fc_geni_uart.ko'
missing={s.split()[-1] for s in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(p)],text=True).splitlines()}
exports={s.split()[1] for s in (sdk/'vmlinux.symvers').read_text().splitlines()}
assert not missing-exports,missing-exports
record={'status':'LIVE_CANDIDATE_NOT_LOADED','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'adapted_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'module_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'scope':'Only the unbound 898000.serial device; separate UART/driver name; original console driver remains registered',
        'reason':'of_alias_get_highest_id returns -ENODEV when ABL DT lacks aliases; clamp allocator lower bound to zero'}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2),flush=True)
