#!/usr/bin/env python3
"""Compile native 60/120/144 Hz panel modes as an offline, never-loaded candidate."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',default='out/native-refresh69')
args=parser.parse_args()
native=json.loads((root/'out/native-display-mode68.json').read_text())
timing=next(n for n in native if n['path'].endswith('/timing@0'))['props']
cell=lambda p,key:p[key]['cells'][0]
width=cell(timing,'qcom,mdss-dsi-panel-width')
height=cell(timing,'qcom,mdss-dsi-panel-height')
hsync=cell(timing,'qcom,mdss-dsi-h-pulse-width')
vsync=cell(timing,'qcom,mdss-dsi-v-pulse-width')
assert (width,height,hsync,vsync)==(1752,2190,16,4)
dfps={cell(n['props'],'fps'):{k:cell(n['props'],k) for k in ('vfp','vbp','hfp','hbp')}
      for n in native if 'fps' in n['props']}
source=root/'kernel/drivers/gpu/drm/panel/panel-novatek-nt36526.c'
original=source.read_text()
assert source.read_bytes()==(root/'port/panel-novatek-nt36526.c').read_bytes()
start=original.index('static const struct drm_display_mode novatek_nt36526_mode = {')
end=original.index('\nstatic const struct drm_panel_funcs',start)
blocks=[];modes=[]
for fps in (120,60,144):
    p=dfps[fps]
    ht=(width+p['hfp']+hsync+p['hbp'])*2;vt=height+p['vfp']+vsync+p['vbp']
    clock=ht*vt*fps//1000
    mode={'refresh_hz':fps,'clock_khz':clock,'hdisplay':width*2,
          'hsync_start':(width+p['hfp'])*2,'hsync_end':(width+p['hfp']+hsync)*2,'htotal':ht,
          'vdisplay':height,'vsync_start':height+p['vfp'],'vsync_end':height+p['vfp']+vsync,'vtotal':vt}
    blocks.append('\t{\n'+''.join('\t\t.'+('clock' if key=='clock_khz' else key)+' = '+str(value)+',\n' for key,value in mode.items() if key!='refresh_hz')+
                  '\t\t.type = DRM_MODE_TYPE_DRIVER'+(' | DRM_MODE_TYPE_PREFERRED' if fps==120 else '')+',\n\t},')
    modes.append(mode)
assert modes[0]['clock_khz']==modes[1]['clock_khz']==1117910
replacement='''/* Native Android dfps-timings; preferred 120 Hz remains unchanged. */
static const struct drm_display_mode novatek_nt36526_modes[] = {
'''+('\n'.join(blocks))+'''
};

static int novatek_nt36526_get_modes(struct drm_panel *panel,
				     struct drm_connector *connector)
{
	struct drm_display_mode *mode;
	unsigned int i;

	connector->display_info.width_mm = 280;
	connector->display_info.height_mm = 175;
	connector->display_info.bpc = 10;
	for (i = 0; i < ARRAY_SIZE(novatek_nt36526_modes); i++) {
		mode = drm_mode_duplicate(connector->dev, &novatek_nt36526_modes[i]);
		if (!mode)
			return -ENOMEM;
		drm_mode_set_name(mode);
		drm_mode_probed_add(connector, mode);
	}
	return ARRAY_SIZE(novatek_nt36526_modes);
}
'''
adapted=original[:start]+replacement+original[end:]
work=(root/args.output).resolve()
assert work.parent==root/'out' and work.name.startswith('native-refresh69')
work.mkdir(exist_ok=False)
path=work/'panel-novatek-nt36526-refresh69.c';path.write_text(adapted)
(work/'Makefile').write_text('obj-m += panel-novatek-nt36526-refresh69.o\n')
sdk=root/'out/kernel-peripherals68'
(sdk/'Module.symvers').write_bytes((sdk/'vmlinux.symvers').read_bytes())
env=dict(os.environ,ARCH='arm64',CROSS_COMPILE='aarch64-linux-gnu-')
subprocess.run(['make','-C',str(root/'kernel'),'O='+str(sdk),'LOCALVERSION=+','-j2','M='+str(work),'modules'],check=True,env=env)
record={'status':'OFFLINE_COMPILED_ONLY_NEVER_LOADED_NO_DISPLAY_REBIND',
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'native_timing_sha256':hashlib.sha256((root/'out/native-display-mode68.json').read_bytes()).hexdigest(),
        'candidate_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'module_sha256':hashlib.sha256((work/'panel-novatek-nt36526-refresh69.ko').read_bytes()).hexdigest(),
        'modes':modes,'scope':'Native porch/clock table only; DSC, initialization, regulators and dual-backlight code preserved',
        'required_acceptance':['Integrate in a separate kernel candidate','Real modeset each refresh rate','Measure actual vblank cadence','Verify screen stability and touch'],
        'risk':'Adding modes alone may be insufficient for vendor custom dynamic-fps switching; untested on hardware'}
(work/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
