#!/usr/bin/env python3
"""Build the codec IRQ-lifetime fix and preserve the validated microphone modules."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
kernel=root/'kernel'
work=root/'out/microphone72'
work.mkdir(exist_ok=False)
codec=work/'codec';codec.mkdir()
base=root/'out/live-microphone71'
original=json.loads((base/'manifest.json').read_text())
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
sources={name:(kernel/'sound/soc/codecs'/name).read_text() for name in ['wcd939x.c','wcd939x-sdw.c','wcd939x.h']}
text=dict(sources)
def replace(name,old,new):
    assert text[name].count(old)==1,(name,old[:90])
    text[name]=text[name].replace(old,new)

replace('wcd939x.h','\tstruct irq_domain *slave_irq;','''\t/* Serialize callback completion with codec IRQ-domain removal. */
\tstruct mutex irq_lock;
\tstruct irq_domain *slave_irq;''')
replace('wcd939x-sdw.c','''\treturn wcd_interrupt_callback(slave, wcd->slave_irq, WCD939X_DIGITAL_INTR_STATUS_0,
\t\t\tWCD939X_DIGITAL_INTR_STATUS_1, WCD939X_DIGITAL_INTR_STATUS_2);''','''\tint ret = IRQ_NONE;

\tmutex_lock(&wcd->irq_lock);
\tif (wcd->slave_irq)
\t\tret = wcd_interrupt_callback(slave, wcd->slave_irq,
\t\t\tWCD939X_DIGITAL_INTR_STATUS_0, WCD939X_DIGITAL_INTR_STATUS_1,
\t\t\tWCD939X_DIGITAL_INTR_STATUS_2);
\tmutex_unlock(&wcd->irq_lock);

\treturn ret;''')
replace('wcd939x-sdw.c','''\tif (!wcd)
\t\treturn -ENOMEM;

\t/*''','''\tif (!wcd)
\t\treturn -ENOMEM;
\tmutex_init(&wcd->irq_lock);

\t/*''')
replace('wcd939x.c','static int wcd939x_irq_init(struct wcd939x_priv *wcd, struct device *dev)',
'''static void wcd939x_irq_exit(struct wcd939x_priv *wcd, struct device *dev)
{
\tunsigned int irq;
\tint i;

\tif (!wcd->virq)
\t\treturn;

\t/* The SDW wrapper holds this lock throughout the nested callback. Clear
\t * both pointers and wait for any callback before freeing its domain.
\t * This lock is independent of the SoundWire driver's sdw_dev_lock.
\t */
\tfor (i = 0; i < NUM_CODEC_DAIS; i++) {
\t\tif (!wcd->sdw_priv[i])
\t\t\tcontinue;
\t\tmutex_lock(&wcd->sdw_priv[i]->irq_lock);
\t\twcd->sdw_priv[i]->slave_irq = NULL;
\t\tmutex_unlock(&wcd->sdw_priv[i]->irq_lock);
\t}

\tirq = irq_find_mapping(wcd->virq, 0);
\tif (wcd->irq_chip) {
\t\tdevm_regmap_del_irq_chip(dev, irq, wcd->irq_chip);
\t\twcd->irq_chip = NULL;
\t}
\tif (irq)
\t\tirq_dispose_mapping(irq);
\tirq_domain_remove(wcd->virq);
\twcd->virq = NULL;
}

static int wcd939x_irq_init(struct wcd939x_priv *wcd, struct device *dev)''')
replace('wcd939x.c','''{
\twcd->virq = irq_domain_create_linear(NULL, 1, &wcd_domain_ops, NULL);''','''{
\tunsigned int irq;
\tint ret;

\twcd->virq = irq_domain_create_linear(NULL, 1, &wcd_domain_ops, NULL);''')
replace('wcd939x.c','''\treturn devm_regmap_add_irq_chip(dev, wcd->regmap,
\t\t\t\t\tirq_create_mapping(wcd->virq, 0),
\t\t\t\t\tIRQF_ONESHOT, 0, &wcd939x_regmap_irq_chip,
\t\t\t\t\t&wcd->irq_chip);''','''\tirq = irq_create_mapping(wcd->virq, 0);
\tif (!irq) {
\t\twcd939x_irq_exit(wcd, dev);
\t\treturn -ENOMEM;
\t}
\tret = devm_regmap_add_irq_chip(dev, wcd->regmap, irq,
\t\t\t\t       IRQF_ONESHOT, 0, &wcd939x_regmap_irq_chip,
\t\t\t\t       &wcd->irq_chip);
\tif (ret)
\t\twcd939x_irq_exit(wcd, dev);
\treturn ret;''')
replace('wcd939x.c','''\twcd939x->sdw_priv[AIF1_PB]->slave_irq = wcd939x->virq;
\twcd939x->sdw_priv[AIF1_CAP]->slave_irq = wcd939x->virq;''','''\tmutex_lock(&wcd939x->sdw_priv[AIF1_PB]->irq_lock);
\twcd939x->sdw_priv[AIF1_PB]->slave_irq = wcd939x->virq;
\tmutex_unlock(&wcd939x->sdw_priv[AIF1_PB]->irq_lock);
\tmutex_lock(&wcd939x->sdw_priv[AIF1_CAP]->irq_lock);
\twcd939x->sdw_priv[AIF1_CAP]->slave_irq = wcd939x->virq;
\tmutex_unlock(&wcd939x->sdw_priv[AIF1_CAP]->irq_lock);''')
replace('wcd939x.c','''\t\tdev_err(dev, "%s: Codec registration failed\\n",
\t\t\t__func__);
\t\tgoto err_remove_rx_link;''','''\t\tdev_err(dev, "%s: Codec registration failed\\n",
\t\t\t__func__);
\t\twcd939x_irq_exit(wcd939x, dev);
\t\tgoto err_remove_rx_link;''')
replace('wcd939x.c','''\tsnd_soc_unregister_component(dev);
\tdevice_link_remove(dev, wcd939x->txdev);''','''\tsnd_soc_unregister_component(dev);
\twcd939x_irq_exit(wcd939x, dev);
\tdevice_link_remove(dev, wcd939x->txdev);''')
patch=[]
for name in sources:
    patch.extend(difflib.unified_diff(sources[name].splitlines(True),text[name].splitlines(True),
                 fromfile='a/sound/soc/codecs/'+name,tofile='b/sound/soc/codecs/'+name))
(work/'wcd939x-irq-lifetime.patch').write_text(''.join(patch))
for header in (kernel/'sound/soc/codecs').glob('*.h'):
    shutil.copy2(header,codec/header.name)
for name,value in text.items(): (codec/name).write_text(value)
(codec/'Makefile').write_text('obj-m += snd-soc-wcd939x.o snd-soc-wcd939x-sdw.o\nsnd-soc-wcd939x-y := wcd939x.o\nsnd-soc-wcd939x-sdw-y := wcd939x-sdw.o\n')
tables=[base/'base-sound.symvers',base/'base-soundwire.symvers',
        kernel/'sound/soc/codecs/Module.symvers',base/'regmap/Module.symvers']
symbols={}
for table in tables:
    for line in table.read_text().splitlines():
        fields=line.split()
        if Path(fields[2]).name not in ['snd-soc-wcd939x','snd-soc-wcd939x-sdw']:
            symbols[fields[1]]=line
extra=work/'extra.symvers';extra.write_text('\n'.join(symbols.values())+'\n')
sdk=root/'out/module-microphone-sdk71'
(sdk/'Module.symvers').write_bytes((root/'out/kernel-usbc70b/vmlinux.symvers').read_bytes())
subprocess.run(['make','-C',str(kernel),'O='+str(sdk),'LOCALVERSION=+','-j2',
                'M='+str(codec),'KBUILD_EXTRA_SYMBOLS='+str(extra),'modules'],check=True,
               env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-'))
modules=work/'modules';modules.mkdir()
record={'status':'IRQ_LIFETIME_FIX_BUILT_NOT_LOADED','base_kernel_image_sha256':original['base_kernel_image_sha256'],
        'modules':{},'sources':{name:{'before_sha256':hashlib.sha256(sources[name].encode()).hexdigest(),
                                    'after_sha256':sha(codec/name)} for name in sources},
        'patch_sha256':sha(work/'wcd939x-irq-lifetime.patch'),
        'scope':'Only codec+SDW-private IRQ lifetime; no live reload, controller replacement, sound core changes or recording'}
for name,entry in original['modules'].items():
    source=codec/name if name in ['snd-soc-wcd939x.ko','snd-soc-wcd939x-sdw.ko'] else base/'modules'/name
    if source.parent!=codec: assert sha(source)==entry['sha256']
    target=modules/name;shutil.copy2(source,target)
    magic=subprocess.check_output(['modinfo','-F','vermagic',str(target)],text=True).strip()
    assert magic==entry['vermagic']
    imports=[line.split()[-1] for line in subprocess.check_output(['aarch64-linux-gnu-nm','-u',str(target)],text=True).splitlines()]
    exports=[line.split()[-1].removeprefix('__ksymtab_') for line in subprocess.check_output(['aarch64-linux-gnu-nm',str(target)],text=True).splitlines()
             if line.split() and line.split()[-1].startswith('__ksymtab_')]
    record['modules'][name]={'sha256':sha(target),'vermagic':magic,'imports':imports,'exports':exports}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'status':record['status'],'module_count':len(record['modules']),'patch_sha256':record['patch_sha256']},indent=2))
