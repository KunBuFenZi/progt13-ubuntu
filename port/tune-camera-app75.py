#!/usr/bin/env python3
"""Add sensor-specific stock colour transforms and optional shades-of-grey AWB."""
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parent.parent
src = next((root / 'out/camera-app75').glob('libcamera-v0.7.0-*'))

with tarfile.open(root / 'reference/camera75/libcamera_0.7.0.orig.tar.gz') as archive:
    for name in ['src/ipa/simple/algorithms/awb.h', 'src/ipa/simple/algorithms/awb.cpp',
                 'include/libcamera/internal/software_isp/swisp_stats.h',
                 'src/libcamera/software_isp/swstats_cpu.cpp', 'src/ipa/simple/soft_simple.cpp']:
        (src / name).write_bytes(archive.extractfile(src.name + '/' + name).read())


def change(path, old, new):
    data = path.read_text()
    if new in data:
        return
    assert data.count(old) == 1, (str(path), data.count(old))
    path.write_text(data.replace(old, new))


# Histograms retain black-relative moments without assuming that dark coloured
# furniture has the average colour of the illuminant. Only these two YAML files
# enable p=4; all other cameras retain the original grey-world algorithm.
change(src / 'include/libcamera/internal/software_isp/swisp_stats.h',
       '\tRGB<uint64_t> sum_;',
       '\tRGB<uint64_t> sum_;\n\tstd::array<std::array<uint32_t, 256>, 3> rgbHistogram;')
stats = src / 'src/libcamera/software_isp/swstats_cpu.cpp'
change(stats, '\tsumB += b;', '''\tsumB += b;                         \\
\tstats_.rgbHistogram[0][r / (div)]++; \\
\tstats_.rgbHistogram[1][g / (div)]++; \\
\tstats_.rgbHistogram[2][b / (div)]++;''')
change(stats, '\tstats_.yHistogram.fill(0);',
       '\tstats_.yHistogram.fill(0);\n\tfor (auto &channel : stats_.rgbHistogram)\n\t\tchannel.fill(0);')
awb_h = src / 'src/ipa/simple/algorithms/awb.h'
change(awb_h, '\tint configure(IPAContext &context,',
       '\tint init(IPAContext &context, const YamlObject &tuningData) override;\n\tint configure(IPAContext &context,')
change(awb_h, '\tvoid prepare(IPAContext &context,',
       '\tvoid queueRequest(IPAContext &context, uint32_t frame, IPAFrameContext &frameContext, const ControlList &controls) override;\n\tvoid prepare(IPAContext &context,')
change(awb_h, '\t\t     ControlList &metadata) override;\n};',
       '\t\t     ControlList &metadata) override;\nprivate:\n\tunsigned int moment_ = 1;\n};')
change(awb_h, '\tunsigned int moment_ = 1;',
       '\tunsigned int moment_ = 1;\n\tstd::vector<RGB<float>> whiteCurve_;')
change(awb_h, '\tunsigned int moment_ = 1;', '\tunsigned int moment_ = 1;\n\tbool autoEnabled_ = true;')
change(awb_h, '#include "algorithm.h"', '#include "algorithm.h"\n#include <vector>')
awb = src / 'src/ipa/simple/algorithms/awb.cpp'
change(awb, '#include <numeric>', '#include <numeric>\n#include <cmath>')
change(awb, 'int Awb::configure(IPAContext &context,', '''int Awb::init([[maybe_unused]] IPAContext &context, const YamlObject &tuningData)
{
\tmoment_ = tuningData["moment"].get<unsigned int>(1);
\tif (moment_ != 1 && moment_ != 4)
\t\treturn -EINVAL;
\treturn 0;
}

int Awb::configure(IPAContext &context,''')
anchor = '\tRGB<double> rgbGains{ { 1 / gains.r(), 1 / gains.g(), 1 / gains.b() } };'
change(awb, anchor, '''\tif (moment_ == 4) {
\t\tstd::array<double, 3> moments{};
\t\tfor (unsigned int c = 0; c < 3; c++)
\t\t\tfor (unsigned int i = blackLevel + 1; i < 250; i++) {
\t\t\t\tconst double signal = i - blackLevel;
\t\t\t\tmoments[c] += stats->rgbHistogram[c][i] * std::pow(signal, 4);
\t\t\t}
\t\tif (moments[0] > 0 && moments[1] > 0 && moments[2] > 0)
\t\t\tgains = { { std::clamp(static_cast<float>(std::pow(moments[1] / moments[0], 0.25)), 0.25f, 4.0f),
\t\t\t\t    1.0f,
\t\t\t\t    std::clamp(static_cast<float>(std::pow(moments[1] / moments[2], 0.25)), 0.25f, 4.0f) } };
\t}

''' + anchor)
change(awb, '\tmoment_ = tuningData["moment"].get<unsigned int>(1);',
       '''\tmoment_ = tuningData["moment"].get<unsigned int>(1);
\tfor (const auto &point : tuningData["whiteCurve"].asList())
\t\twhiteCurve_.push_back(RGB<float>({ point["r"].get<float>(1), 1.0f, point["b"].get<float>(1) }));''')
change(awb, anchor, '''\tif (whiteCurve_.size() >= 2) {
\t\tfloat bestDistance = std::numeric_limits<float>::max();
\t\tRGB<float> bestGains = gains;
\t\tfor (unsigned int i = 1; i < whiteCurve_.size(); i++) {
\t\t\tconst auto &a = whiteCurve_[i - 1];
\t\t\tconst auto &b = whiteCurve_[i];
\t\t\tconst float ar = std::log(a.r()), ab = std::log(a.b());
\t\t\tconst float dr = std::log(b.r()) - ar, db = std::log(b.b()) - ab;
\t\t\tconst float t = std::clamp(((std::log(gains.r()) - ar) * dr + (std::log(gains.b()) - ab) * db) / (dr * dr + db * db), 0.0f, 1.0f);
\t\t\tconst float rr = ar + t * dr, bb = ab + t * db;
\t\t\tconst float distance = std::pow(rr - std::log(gains.r()), 2) + std::pow(bb - std::log(gains.b()), 2);
\t\t\tif (distance < bestDistance) {
\t\t\t\tbestDistance = distance;
\t\t\t\tbestGains = { { std::exp(rr), 1.0f, std::exp(bb) } };
\t\t\t}
\t\t}
\t\tgains = bestGains;
\t}

''' + anchor)
change(awb, '#include <cmath>', '#include <cmath>\n#include <limits>')
change(awb, 'int Awb::init([[maybe_unused]] IPAContext &context,',
       'int Awb::init(IPAContext &context,')
change(awb, '\tmoment_ = tuningData["moment"].get<unsigned int>(1);',
       '\tcontext.ctrlMap[&controls::AwbEnable] = ControlInfo(false, true, true);\n\tcontext.ctrlMap[&controls::ColourGains] = ControlInfo(0.25f, 4.0f);\n\tmoment_ = tuningData["moment"].get<unsigned int>(1);')
change(awb, '\tauto &gains = context.activeState.awb.gains;\n\tgains = { { 1.0, 1.0, 1.0 } };',
       '\tauto &gains = context.activeState.awb.gains;\n\tautoEnabled_ = true;\n\tgains = { { 1.0, 1.0, 1.0 } };')
change(awb, 'void Awb::prepare(IPAContext &context,',
       '''void Awb::queueRequest(IPAContext &context, [[maybe_unused]] uint32_t frame,
                       [[maybe_unused]] IPAFrameContext &frameContext, const ControlList &requestControls)
{
\tif (const auto enable = requestControls.get(controls::AwbEnable))
\t\tautoEnabled_ = *enable;
\tif (!autoEnabled_)
\t\tif (const auto gains = requestControls.get(controls::ColourGains))
\t\t\tcontext.activeState.awb.gains = { { std::clamp((*gains)[0], 0.25f, 4.0f), 1.0f, std::clamp((*gains)[1], 0.25f, 4.0f) } };
}

void Awb::prepare(IPAContext &context,''')
change(awb, '\tif (!stats->valid)\n\t\treturn;',
       '\tmetadata.set(controls::AwbEnable, autoEnabled_);\n\tif (!stats->valid || !autoEnabled_)\n\t\treturn;')

# A CCM must transform the black-relative signal, not the optical pedestal.
# Keep negative cross-channel coefficients; clip only the final RGB sum.
cpu = src / 'src/libcamera/software_isp/debayer_cpu.cpp'
change(cpu, '\t\t\tfor (unsigned int i = 0; i < kRGBLookupSize; i++) {\n\t\t\t\tred[i].r',
       '\t\t\tconst float pedestal = params.blackLevel.g() * gammaTableSize * div;\n\t\t\tfor (unsigned int i = 0; i < kRGBLookupSize; i++) {\n\t\t\t\tconst float signal = std::max(static_cast<float>(i) - pedestal, 0.0f);\n\t\t\t\tred[i].r')
for channel in ['red', 'green', 'blue']:
    for component in ['r', 'g', 'b']:
        # Replace only the exact nine coefficient assignments, not other uses.
        import re
        data = cpu.read_text()
        data = re.sub(r'(' + channel + r'\[i\]\.' + component + r' = std::round\()i( \* params\.combinedMatrix)', r'\1signal\2', data)
        cpu.write_text(data)
change(cpu, '\t\t\t\tgammaLut_[i] = gammaTable_[i / div];',
       '\t\t\t\tgammaLut_[i] = gammaTable_[std::min(static_cast<unsigned int>((i + pedestal) / div), gammaTableSize - 1)];')
ipa = src / 'src/ipa/simple/soft_simple.cpp'
change(ipa, '\t\tparams_->gains = { { 1.0, 1.0, 1.0 } };',
       '\t\tparams_->gains = { { 1.0, 1.0, 1.0 } };\n\t\tparams_->combinedMatrix = Matrix<float, 3, 3>::identity();')

# With a slower full-size ISP, output buffers can finish before async metadata.
# Stop must cancel those requests too, rather than discard their only record.
simple = src / 'src/libcamera/pipeline/simple/simple.cpp'
change(simple, '\tvoid clear();\n\n\tSimpleFrameInfo *find',
       '\tvoid clear();\n\tstd::vector<Request *> takeRequests();\n\n\tSimpleFrameInfo *find')
change(simple, 'SimpleFrameInfo *SimpleFrames::find(uint32_t frame)',
       '''std::vector<Request *> SimpleFrames::takeRequests()
{
\tstd::vector<Request *> requests;
\tfor (auto &[frame, info] : frameInfo_)
\t\trequests.push_back(info.request);
\tframeInfo_.clear();
\treturn requests;
}

SimpleFrameInfo *SimpleFrames::find(uint32_t frame)''')
change(simple, '\t\tpipe()->cancelRequest(conversionQueue_.front().request);',
       '\t\tframeInfo_.destroy(conversionQueue_.front().request->sequence());\n\t\tpipe()->cancelRequest(conversionQueue_.front().request);')
change(simple, '\tdata->frameInfo_.clear();\n\tdata->clearIncompleteRequests();',
       '\tdata->clearIncompleteRequests();\n\tfor (Request *request : data->frameInfo_.takeRequests())\n\t\tcancelRequest(request);')

calibration = json.loads((root / 'reference/camera75/stock-colour-matrices.json').read_text())
data_dir = src / 'src/ipa/simple/data'
for sensor, item in calibration['sensors'].items():
    text = '# SPDX-License-Identifier: CC0-1.0\n%YAML 1.1\n---\nversion: 1\nalgorithms:\n  - BlackLevel:\n      blackLevel: 4096\n  - Awb:\n      moment: 4\n      whiteCurve:\n'
    for point in item['white_curve']:
        text += f"        - r: {point['r']:.9f}\n          b: {point['b']:.9f}\n"
    text += '  - Ccm:\n      ccms:\n'
    for matrix in item['ccms']:
        text += f"        - ct: {matrix['ct']}\n          ccm: [" + ', '.join(f'{v:.9f}' for v in matrix['linear_srgb']) + ']\n'
    text += '  - Adjust:\n  - Agc:\n...\n'
    (data_dir / (sensor + '.yaml')).write_text(text)
change(data_dir / 'meson.build', "    'uncalibrated.yaml',",
       "    'uncalibrated.yaml',\n    'gc08a8.yaml',\n    'ov13b10.yaml',")
print('Stock sensor colour matrices and image statistics configured')
