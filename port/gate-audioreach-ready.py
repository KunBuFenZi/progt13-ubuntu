#!/usr/bin/env python3
"""Defer card/topology construction until SPF is ready and APR can receive."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
p = root/'kernel/sound/soc/qcom/qdsp6/q6apm.c'
s = p.read_text()
old = '\tif (!g_apm)\n\t\treturn false;'
new = '\tif (!g_apm || !READ_ONCE(g_apm->gdev->svc.callback))\n\t\treturn false;'
if old in s:
    assert s.count(old) == 1
    s = s.replace(old,new)
else:
    assert new in s
old = '''static int q6apm_audio_probe(struct snd_soc_component *component)
{
\treturn audioreach_tplg_init(component);
}'''
new = '''static int q6apm_audio_probe(struct snd_soc_component *component)
{
\t/* PCM construction maps buffers into the DSP; it must not race SPF boot. */
\tif (!q6apm_is_adsp_ready())
\t\treturn -EPROBE_DEFER;

\treturn audioreach_tplg_init(component);
}'''
if old in s:
    assert s.count(old) == 1
    s = s.replace(old,new)
else:
    assert new in s
p.write_text(s)
print('Card construction waits for a live APR callback and positive SPF state')
