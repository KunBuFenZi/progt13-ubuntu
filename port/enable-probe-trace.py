#!/usr/bin/env python3
"""Add bounded-scope debug prints to the pinned kernel's device probe paths."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def replace_once(path, old, new, marker):
    text = path.read_text()
    if marker in text:
        return
    assert text.count(old) == 1, f'Pinned source context changed: {path}'
    path.write_text(text.replace(old, new, 1))


dd = ROOT / 'kernel/drivers/base/dd.c'
replace_once(dd,
    '\tcalltime = ktime_get();\n\tret = really_probe(dev, drv);\n\trettime = ktime_get();',
    '\tprintk(KERN_INFO "TBPROBE B %s [%s]\\n", dev_name(dev), drv->name);\n'
    '\tcalltime = ktime_get();\n\tret = really_probe(dev, drv);\n\trettime = ktime_get();\n'
    '\tprintk(KERN_INFO "TBPROBE E %s [%s] ret=%d\\n", dev_name(dev), drv->name, ret);',
    'TBPROBE B')
text = dd.read_text()
if 'TBDEFER' not in text:
    start = text.index('static int deferred_probe_initcall(void)')
    end = text.index('late_initcall(deferred_probe_initcall);', start)
    body = text[start:end]
    assert body.count('\tflush_work(&deferred_probe_work);') == 2
    for phase in (1, 2):
        old = '\tflush_work(&deferred_probe_work);'
        # Search the original call after the preceding inserted marker.
        pos = body.find(old, 0 if phase == 1 else body.index('TBDEFER 1 E'))
        new = (f'\tif (initcall_debug)\n\t\tpr_info("TBDEFER {phase} B\\n");\n'
               + old + f'\n\tif (initcall_debug)\n\t\tpr_info("TBDEFER {phase} E\\n");')
        body = body[:pos] + new + body[pos + len(old):]
    dd.write_text(text[:start] + body + text[end:])

replace_once(ROOT / 'kernel/drivers/base/core.c',
    '\t\tdev_sync_state(dev);',
    '\t\tif (initcall_debug)\n\t\t\tpr_info("TBSYNC B %s\\n", dev_name(dev));\n'
    '\t\tdev_sync_state(dev);\n'
    '\t\tif (initcall_debug)\n\t\t\tpr_info("TBSYNC E %s\\n", dev_name(dev));',
    'TBSYNC B')
print('PROBE_TRACE_SOURCE_READY')
