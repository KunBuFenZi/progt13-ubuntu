# SPDX-License-Identifier: BSD-3-Clause
# Based on Linaro's AudioReach topology and the pinned OnePlus TDM helpers.
# TB378FC's native PAL profile is 48kHz / 4 channels / S32_LE.
include(`audioreach/audioreach.m4')
include(`audioreach/stream-subgraph.m4')
include(`util/route.m4')
include(`util/mixer.m4')
include(`audioreach/tokens.m4')
include(`audioreach/module_tdm.m4')
include(`audioreach/module_mfc_cfg.m4')

STREAM_SG_PCM_ADD(audioreach/subgraph-stream-vol-playback.m4, FRONTEND_DAI_MULTIMEDIA1,
    `S16_LE', 48000, 48000, 2, 2,
    0x00004001, 0x00004001, 0x00006001, `110000')

define(`NAME_PREFIX', `device40') dnl
AR_SUBGRAPH(1, SECONDARY_TDM_RX_0, 0x00004010,
    APM_SG_PERF_MODE_LOW_LATENCY, APM_SUB_GRAPH_DIRECTION_TX, APM_SUB_GRAPH_SID_AUDIO_PLAYBACK)
AR_CONTAINER(1, 0x00004010, APM_CONTAINER_TYPE_ID_GC, 8192,
    APM_CONT_GRAPH_POS_STREAM, APM_PROC_DOMAIN_ID_ADSP)
AR_MODULE_LOG(1, 1, 1, 0x00006100, 1, 1, 1, 2, 0x000019ab, 1, 0, 0x00006101)
AR_MODULE_MFC_CFG(1, 1, 1, 0x00006101, 1, 1, 1, 2, 0x00006102)
AR_MODULE_TDM_RX(1, 1, 1, 0x00006102, LPAIF_INTF_TYPE_LPAIF, I2S_INTF_TYPE_SECONDARY,
    DATA_FORMAT_FIXED_POINT, 0x0f, 4, 32, 2, 1, 1, 0, 0, 0, `Secondary TDM0')

# Default four-channel DSP map is FL FR LS RS = 1 2 4 5.
# Actual board slots are left-down, left-up, right-up, right-down.
# One stereo input therefore maps L,L,R,R, with one Q14 unity entry per row.
# Param size 36 excludes the final four-byte alignment pad.
SectionData."device40.mfc1_cfg" {
    words "0x00000048, 0x01001006, 0x00000000, 0x00000000,
        0x00006101, 0x0800101f, 0x00000024, 0x00000000,
        0x00000001, 0x00020004,
        0x00020001, 0x00050004,
        0x00020001,
        0x00004000, 0x00004000, 0x40000000, 0x40000000,
        0x00000000"
}

SectionGraph."Secondary TDM0 Hardware Graph" {
    index "1"
    lines [
        "device40.logger1, , Secondary TDM0 Audio Mixer"
        "device40.mfc1, , device40.logger1"
        "device40.tdm_rx1, , device40.mfc1"
        "Secondary TDM0 Playback, , device40.tdm_rx1"
    ]
}
STREAM_DEVICE_PLAYBACK_MIXER(SECONDARY_TDM_RX_0, ``Secondary TDM0'', ``MultiMedia1'')
STREAM_DEVICE_PLAYBACK_ROUTE(SECONDARY_TDM_RX_0, ``Secondary TDM0 Audio Mixer'', ``MultiMedia1, stream0.logger1'')
