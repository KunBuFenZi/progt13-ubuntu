#!/usr/bin/env python3
"""Use driver-core deferred probe, rather than ASoC's component wait list."""
from pathlib import Path

root=Path(__file__).resolve().parent.parent
p=root/'kernel/sound/soc/qcom/qdsp6/q6apm.c'
s=p.read_text()
old='''static int q6apm_audio_probe(struct snd_soc_component *component)
{
\t/* PCM construction maps buffers into the DSP; it must not race SPF boot. */
\tif (!q6apm_is_adsp_ready())
\t\treturn -EPROBE_DEFER;

\treturn audioreach_tplg_init(component);
}'''
new='''static int q6apm_audio_probe(struct snd_soc_component *component)
{
\treturn audioreach_tplg_init(component);
}'''
if old in s:
    s=s.replace(old,new)
else:
    assert new in s
p.write_text(s)
p=root/'kernel/sound/soc/qcom/qdsp6/q6apm-dai.c'
s=p.read_text()
old='''\tint rc;

\tpdata = devm_kzalloc(dev, sizeof(*pdata), GFP_KERNEL);'''
new='''\tint rc;

\t/* Registering the FE can bind a card and map PCM buffers immediately.
\t * Defer this platform device so the driver core retries after SPF boot.
\t */
\tif (!q6apm_is_adsp_ready())
\t\treturn -EPROBE_DEFER;

\tpdata = devm_kzalloc(dev, sizeof(*pdata), GFP_KERNEL);'''
if old in s:
    assert s.count(old)==1
    s=s.replace(old,new)
else:
    assert new in s
p.write_text(s)
print('SPF readiness gates FE platform registration; normal driver-core retries apply')
