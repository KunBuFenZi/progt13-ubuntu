#!/usr/bin/env python3
"""Build isolated libcamera helpers and a CAMSS frame-alignment fix, without loading."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parent.parent
work = root / 'out/camera-app75'
src = next(work.glob('libcamera-v0.7.0-*'))
sdk = root / 'out/mesa-root-build/root'
extra = work / 'sdk'
native = work / 'native'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
patches = []

def change(path, old, new):
    before = path.read_text()
    if new in before:
        return
    if old not in before:
        assert new in before, path
        return
    assert before.count(old) == 1, (path, before.count(old))
    after = before.replace(old, new)
    path.write_text(after)
    patches.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                      fromfile=str(path.relative_to(root)), tofile=str(path.relative_to(root))))

# The running Ubuntu library has no gain models for either sensor. Both use
# raw gain register units; their optical pedestal is 64 in the observed RAW10.
helpers = src / 'src/ipa/libipa/camera_sensor_helper.cpp'
anchor = 'REGISTER_CAMERA_SENSOR_HELPER("ov13858", CameraSensorHelperOv13858)'
models = ''
for sensor, denominator in [('Gc08a8', 1024), ('Ov13b10', 128)]:
    models += f'''

class CameraSensorHelper{sensor} : public CameraSensorHelper
{{
public:
\tCameraSensorHelper{sensor}()
\t{{
\t\tblackLevel_ = 4096;
\t\tgain_ = AnalogueGainLinear{{ 1, 0, 0, {denominator} }};
\t}}
}};
REGISTER_CAMERA_SENSOR_HELPER("{sensor.lower()}", CameraSensorHelper{sensor})'''
change(helpers, anchor + '\n\nclass CameraSensorHelperVd55g1',
       anchor + models + '\n\nclass CameraSensorHelperVd55g1')

# Android's board rotation values describe a portrait natural display. The
# current temporary DT retained them, while this desktop is landscape native.
# Scope the runtime correction to this board, and only its old DT values.
legacy = src / 'src/libcamera/sensor/camera_sensor_legacy.cpp'
with tarfile.open(root / 'reference/camera75/libcamera_0.7.0.orig.tar.gz') as archive:
    baseline = archive.extractfile(src.name + '/src/libcamera/sensor/camera_sensor_legacy.cpp').read()
legacy.write_bytes(baseline)
change(legacy, '#include <algorithm>', '#include <algorithm>\n#include <fstream>')
change(legacy,
       '\t\tint32_t propertyValue = rotationControl->second.def().get<int32_t>();',
       '''\t\tint32_t propertyValue = rotationControl->second.def().get<int32_t>();
\t\tstd::ifstream boardCamera("/proc/device-tree/soc@0/cci@ac7b000/i2c-bus@0/camera@36/compatible");
\t\tstd::string boardCompatible;
\t\tstd::getline(boardCamera, boardCompatible, '\\0');
\t\tif (boardCompatible == "lenovo,tb378fc-ov13b10" &&
\t\t    ((model_ == "gc08a8" && propertyValue == 270) ||
\t\t     (model_ == "ov13b10" && propertyValue == 90)))
\t\t\tpropertyValue = 0;''')

# A failed early start must not block waiting on an ISP worker that was never
# started. Return internal QBUF errors instead of reporting a working stream.
change(src / 'src/libcamera/software_isp/software_isp.cpp',
       'void SoftwareIsp::stop()\n{\n\tdebayer_->invokeMethod',
       'void SoftwareIsp::stop()\n{\n\tif (!ispWorkerThread_.isRunning())\n\t\treturn;\n\n\tdebayer_->invokeMethod')
change(src / 'src/libcamera/software_isp/software_isp.cpp',
       '\tipa_->setIspParams.connect(this, &SoftwareIsp::saveIspParams);',
       '\t/* IPA init supplies defined neutral parameters before its first async response. */\n\tdebayerParams_ = *sharedParams_;\n\n\tipa_->setIspParams.connect(this, &SoftwareIsp::saveIspParams);')
change(src / 'src/libcamera/pipeline/simple/simple.cpp',
       '\t\tif (!data->rawStream_)\n\t\t\tfor (std::unique_ptr<FrameBuffer> &buffer : data->conversionBuffers_)\n\t\t\t\tvideo->queueBuffer(buffer.get());',
       '\t\tif (!data->rawStream_) {\n\t\t\tfor (std::unique_ptr<FrameBuffer> &buffer : data->conversionBuffers_) {\n\t\t\t\tret = video->queueBuffer(buffer.get());\n\t\t\t\tif (ret < 0) {\n\t\t\t\t\tstop(camera);\n\t\t\t\t\treturn ret;\n\t\t\t\t}\n\t\t\t}\n\t\t}')

# Applying AWB to the optical pedestal creates red/blue light from black.
# Move to black-relative coordinates for channel gains, then restore the
# pedestal expected by the shared gamma table. The untuned path has no CCM.
change(src / 'src/libcamera/software_isp/debayer_cpu.cpp',
       '\t\t\t\tconst RGB<float> lutGains = (gains * i / div).min(gammaTableSize - 1);',
       '''\t\t\t\tconst float blackIndex = params.blackLevel.g() * gammaTableSize;
\t\t\t\tconst float signal = std::max(static_cast<float>(i / div) - blackIndex, 0.0f);
\t\t\t\tconst RGB<float> lutGains = (gains * signal + RGB<float>(blackIndex)).min(gammaTableSize - 1);''')

subprocess.run([sys.executable, str(root / 'port/tune-camera-app75.py')], check=True)

# CAMSS gen4 programs frame increments in 256-byte units. Keep line stride
# unchanged and pad only the end of the frame, including QUERYBUF/sizeimage.
camss = work / 'camss'
if not camss.exists():
    shutil.copytree(root / 'out/camera74/camss', camss,
                    ignore=shutil.ignore_patterns('*.o', '*.ko', '*.mod', '*.mod.c', '.*.cmd', 'Module.symvers', 'modules.order'))
header = camss / 'camss-video.h'
double = '\tunsigned int sizeimage_alignment;\n\tunsigned int sizeimage_alignment;'
if double in header.read_text():
    header.write_text(header.read_text().replace(double, '\tunsigned int sizeimage_alignment;'))
change(camss / 'camss-video.h', '\tunsigned int bpl_alignment;',
       '\tunsigned int bpl_alignment;\n\tunsigned int sizeimage_alignment;')
change(camss / 'camss-vfe-gen4.c',
       '\tfor (i = 0; i < vfe->res->line_num; i++)\n\t\tvfe->line[i].video_out.vb2_q.min_queued_buffers = CAMSS_INIT_BUF_COUNT;',
       '\tfor (i = 0; i < vfe->res->line_num; i++) {\n\t\tvfe->line[i].video_out.vb2_q.min_queued_buffers = CAMSS_INIT_BUF_COUNT;\n\t\tvfe->line[i].video_out.sizeimage_alignment = 256;\n\t}')
change(camss / 'camss-vfe-gen4.c',
       'ALIGN(pix->plane_fmt[0].bytesperline, 16) * pix->height >> 8,',
       'pix->plane_fmt[0].sizeimage >> 8,')
change(camss / 'camss-vfe-gen4.c',
       '!IS_ALIGNED(pix->plane_fmt[0].bytesperline * pix->height, 256)',
       '!IS_ALIGNED(pix->plane_fmt[0].sizeimage, 256)')
change(camss / 'camss-video.c',
       '\t\t\tif (p->sizeimage < sizeimage[i])\n\t\t\t\tp->sizeimage = sizeimage[i];\n\t\t}\n\n\treturn 0;',
       '\t\t\tif (p->sizeimage < sizeimage[i])\n\t\t\t\tp->sizeimage = sizeimage[i];\n\t\t}\n\n\tif (video->sizeimage_alignment)\n\t\tfor (i = 0; i < pix_mp->num_planes; i++)\n\t\t\tpix_mp->plane_fmt[i].sizeimage =\n\t\t\t\tALIGN(pix_mp->plane_fmt[i].sizeimage, video->sizeimage_alignment);\n\n\treturn 0;')
if patches:
    p = work / 'changes.patch'
    with p.open('a') as out: out.write(''.join(patches))

env = dict(os.environ, ARCH='arm64', CROSS_COMPILE='aarch64-linux-gnu-')
symvers = work / 'extra.symvers'
symvers.write_text((root / 'out/camera74/extra.symvers').read_text() + ''.join(
    line for line in (root / 'out/camera74/Module.symvers').read_text().splitlines(True)
    if Path(line.split()[2]).name != 'qcom-camss'))
subprocess.run(['make', '-C', str(root / 'kernel'), 'O=' + str(root / 'out/module-camera-sdk74'),
                'M=' + str(camss), 'LOCALVERSION=+', 'KBUILD_EXTRA_SYMBOLS=' + str(symvers),
                'modules', '-j2'], env=env, check=True)

# Keep the established Mesa SDK immutable; layer only the three verified
# dependency packages in a private include/library overlay for this build.
for name in ['libudev', 'yaml-0.1']:
    pc = extra / ('usr/lib/aarch64-linux-gnu/pkgconfig/' + name + '.pc')
    text = pc.read_text().replace('prefix=/usr\n', 'prefix=' + str(extra / 'usr') + '\n')
    pc.write_text(text)
wrapper = work / 'pkg-config'
wrapper.write_text('#!/bin/sh\nexport PKG_CONFIG_SYSROOT_DIR=' + str(sdk) + '\n'
                  'export PKG_CONFIG_LIBDIR=' + str(extra / 'usr/lib/aarch64-linux-gnu/pkgconfig') + ':'
                  + str(sdk / 'usr/lib/aarch64-linux-gnu/pkgconfig') + ':' + str(sdk / 'usr/share/pkgconfig')
                  + '\nexec /usr/bin/pkg-config "$@"\n')
wrapper.chmod(0o755)
cross = work / 'cross.ini'
cross.write_text(f'''[binaries]
c = ['aarch64-linux-gnu-gcc', '--sysroot={sdk}']
cpp = ['aarch64-linux-gnu-g++', '--sysroot={sdk}']
ar = 'aarch64-linux-gnu-ar'
strip = 'aarch64-linux-gnu-strip'
pkg-config = '{wrapper}'
exe_wrapper = ['qemu-aarch64', '-L', '{sdk}']
[host_machine]
system = 'linux'
cpu_family = 'aarch64'
cpu = 'aarch64'
endian = 'little'
[properties]
needs_exe_wrapper = true
''')
env = dict(os.environ, PYTHONPATH=str(native), PYTHONHASHSEED='0')
meson = ['python3', '-m', 'mesonbuild.mesonmain']
prefix = '/usr/lib/tb378fc/camera75'
build = work / 'build'
link_args = json.dumps(['-L' + str(extra / 'usr/lib/aarch64-linux-gnu'),
                        '-L' + str(sdk / 'usr/lib/aarch64-linux-gnu'),
                        '-Wl,-rpath-link,' + str(sdk / 'usr/lib/aarch64-linux-gnu')])
if not (build / 'build.ninja').exists():
    subprocess.run([*meson, 'setup', str(build), str(src), '--cross-file', str(cross),
                    '--prefix=' + prefix, '--libdir=lib', '--buildtype=debugoptimized', '--wrap-mode=nofallback',
                    '-Dpipelines=simple', '-Dipas=simple', '-Dcam=disabled', '-Dqcam=disabled',
                    '-Dgstreamer=disabled', '-Dpycamera=disabled', '-Dlc-compliance=disabled',
                    '-Ddocumentation=disabled', '-Dtracing=disabled', '-Dlibunwind=disabled', '-Dv4l2=disabled',
                    '-Dudev=enabled', '-Dtest=false', '-Dwerror=false',
                    '-Dc_args=-I' + str(extra / 'usr/include'),
                    '-Dcpp_args=-I' + str(extra / 'usr/include'),
                    '-Dc_link_args=' + link_args, '-Dcpp_link_args=' + link_args], env=env, check=True)
else:
    subprocess.run([*meson, 'configure', str(build), '-Dc_link_args=' + link_args,
                    '-Dcpp_link_args=' + link_args], env=env, check=True)
subprocess.run([*meson, 'compile', '-C', str(build), '-j', '2'], env=env, check=True)
subprocess.run([*meson, 'install', '-C', str(build), '--no-rebuild', '--destdir', str(work / 'stage')], env=env, check=True)
print(json.dumps({'status': 'CAMERA75_BUILD_COMPLETE_NOT_LOADED', 'recipe_sha256': sha(__file__)}))
