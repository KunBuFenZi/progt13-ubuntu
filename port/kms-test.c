/* SPDX-License-Identifier: GPL-2.0-only */
/* RAM-only native KMS probe: mode set, color bars, and a real vblank wait. */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>

static void alarm_handler(int sig) { (void)sig; }

static int checked_ioctl(int fd, unsigned long request, void *arg, const char *name)
{
	if (ioctl(fd, request, arg) < 0) {
		fprintf(stderr, "KMS_FAIL %s errno=%d (%s)\n", name, errno, strerror(errno));
		return -1;
	}
	return 0;
}

int main(int argc, char **argv)
{
	uint32_t crtcs[32] = {}, connectors[32] = {}, encoders[32] = {};
	struct drm_mode_card_res res = {};
	struct drm_mode_get_connector conn = {};
	struct drm_mode_modeinfo modes[32] = {}, mode = {};
	struct drm_mode_get_encoder enc = {};
	struct drm_mode_create_dumb dumb = {};
	struct drm_mode_map_dumb map = {};
	struct drm_mode_fb_cmd fb = {};
	struct drm_mode_crtc crtc = {}, active = {}, old = {};
	union drm_wait_vblank vblank = {};
	const uint32_t colors[] = { 0xffffff, 0xffff00, 0x00ffff, 0x00ff00,
				    0xff00ff, 0xff0000, 0x0000ff, 0x202020 };
	uint32_t *pixels;
	uint32_t connector = 0;
	unsigned int i, j, x, y, crtc_index = 0;
	int fd, duration = argc > 1 ? atoi(argv[1]) : 90;
	int black = argc > 3 && !strcmp(argv[3], "black");
	char path[64];

	struct sigaction action = { .sa_handler = alarm_handler };
	setvbuf(stdout, NULL, _IOLBF, 0);
	sigemptyset(&action.sa_mask);
	sigaction(SIGALRM, &action, NULL);
	if (duration < 1 || duration > 300)
		return 2;
	for (i = 0; i < 8; i++) {
		snprintf(path, sizeof(path), "/dev/dri/card%u", i);
		fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0)
			continue;
		memset(&res, 0, sizeof(res));
		res.crtc_id_ptr = (uintptr_t)crtcs;
		res.connector_id_ptr = (uintptr_t)connectors;
		res.count_crtcs = 32;
		res.count_connectors = 32;
		if (ioctl(fd, DRM_IOCTL_MODE_GETRESOURCES, &res) == 0 &&
		    res.count_crtcs && res.count_crtcs <= 32 && res.count_connectors <= 32) {
			printf("KMS_DEVICE %s crtcs=%u connectors=%u\n", path,
				res.count_crtcs, res.count_connectors);
			break;
		}
		close(fd);
	}
	if (i == 8) {
		fprintf(stderr, "KMS_FAIL no KMS device\n");
		return 1;
	}
	for (i = 0; i < res.count_connectors; i++) {
		memset(&conn, 0, sizeof(conn));
		conn.connector_id = connectors[i];
		/* A zero-mode query forces detection on a fresh DRM device. */
		if (checked_ioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, &conn, "PROBE_CONNECTOR"))
			continue;
		if (conn.count_modes > 32 || conn.count_encoders > 32)
			continue;
		conn.modes_ptr = (uintptr_t)modes;
		conn.count_modes = 32;
		conn.encoders_ptr = (uintptr_t)encoders;
		conn.count_encoders = 32;
		/* The sizing query also returned a property count, but this probe
		 * does not request property arrays. Reset it before the data query.
		 */
		conn.count_props = 0;
		if (checked_ioctl(fd, DRM_IOCTL_MODE_GETCONNECTOR, &conn, "GETCONNECTOR"))
			continue;
		printf("KMS_CONNECTOR id=%u type=%u connection=%u modes=%u\n",
			conn.connector_id, conn.connector_type, conn.connection, conn.count_modes);
		/* The GETCONNECTOR UAPI reports drm_connector_status: connected=1. */
		if (conn.connection != 1 || conn.count_modes > 32)
			continue;
		for (j = 0; j < conn.count_modes; j++)
			if (modes[j].hdisplay == 3504 && modes[j].vdisplay == 2190) {
				mode = modes[j];
				connector = conn.connector_id;
				break;
			}
		if (connector)
			break;
	}
	if (!connector || !conn.count_encoders || conn.count_encoders > 32) {
		fprintf(stderr, "KMS_FAIL native panel connector/mode absent\n");
		close(fd);
		return 1;
	}
	for (i = 0; i < conn.count_encoders; i++) {
		enc.encoder_id = encoders[i];
		if (ioctl(fd, DRM_IOCTL_MODE_GETENCODER, &enc) < 0)
			continue;
		for (j = 0; j < res.count_crtcs; j++)
			if (enc.possible_crtcs & (1U << j)) {
				crtc.crtc_id = crtcs[j];
				crtc_index = j;
				break;
			}
		if (crtc.crtc_id)
			break;
	}
	if (!crtc.crtc_id) {
		fprintf(stderr, "KMS_FAIL no compatible CRTC\n");
		close(fd);
		return 1;
	}
	old.crtc_id = crtc.crtc_id;
	ioctl(fd, DRM_IOCTL_MODE_GETCRTC, &old);
	dumb.width = mode.hdisplay;
	dumb.height = mode.vdisplay;
	dumb.bpp = 32;
	if (checked_ioctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &dumb, "CREATE_DUMB"))
		goto fail;
	map.handle = dumb.handle;
	if (checked_ioctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map, "MAP_DUMB"))
		goto fail;
	pixels = mmap(NULL, dumb.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map.offset);
	if (pixels == MAP_FAILED) {
		perror("KMS_FAIL mmap");
		goto fail;
	}
	for (y = 0; y < mode.vdisplay; y++)
		for (x = 0; x < mode.hdisplay; x++)
			pixels[y * (dumb.pitch / 4) + x] = black ? 0 : colors[x * 8 / mode.hdisplay];
	fb.width = mode.hdisplay;
	fb.height = mode.vdisplay;
	fb.pitch = dumb.pitch;
	fb.bpp = 32;
	fb.depth = 24;
	fb.handle = dumb.handle;
	if (checked_ioctl(fd, DRM_IOCTL_MODE_ADDFB, &fb, "ADDFB"))
		goto fail_map;
	crtc.fb_id = fb.fb_id;
	crtc.set_connectors_ptr = (uintptr_t)&connector;
	crtc.count_connectors = 1;
	crtc.mode = mode;
	crtc.mode_valid = 1;
	alarm(15);
	if (checked_ioctl(fd, DRM_IOCTL_MODE_SETCRTC, &crtc, "SETCRTC"))
		goto fail_map;
	alarm(0);
	active.crtc_id = crtc.crtc_id;
	if (checked_ioctl(fd, DRM_IOCTL_MODE_GETCRTC, &active, "GETCRTC"))
		goto restore;
	if (active.fb_id != fb.fb_id || !active.mode_valid ||
	    active.mode.hdisplay != 3504 || active.mode.vdisplay != 2190) {
		fprintf(stderr, "KMS_FAIL active mode differs\n");
		goto restore;
	}
	vblank.request.type = _DRM_VBLANK_RELATIVE | (crtc_index << _DRM_VBLANK_HIGH_CRTC_SHIFT);
	vblank.request.sequence = 1;
	alarm(5);
	if (checked_ioctl(fd, DRM_IOCTL_WAIT_VBLANK, &vblank, "WAIT_VBLANK"))
		goto restore;
	alarm(0);
	printf("TB378FC_KMS_ACTIVE width=%u height=%u fb=%u vblank=%u\n",
		active.mode.hdisplay, active.mode.vdisplay, active.fb_id, vblank.reply.sequence);
	sleep(duration);
	if (argc > 2 && !strcmp(argv[2], "cycle")) {
		struct drm_mode_crtc disabled = { .crtc_id = crtc.crtc_id };

		if (checked_ioctl(fd, DRM_IOCTL_MODE_SETCRTC, &disabled, "DISABLE_CRTC"))
			goto fail_map;
	} else if (old.mode_valid && old.fb_id) {
		old.set_connectors_ptr = (uintptr_t)&connector;
		old.count_connectors = 1;
		ioctl(fd, DRM_IOCTL_MODE_SETCRTC, &old);
	}
	munmap(pixels, dumb.size);
	close(fd);
	return 0;
restore:
	alarm(0);
	if (old.mode_valid && old.fb_id) {
		old.set_connectors_ptr = (uintptr_t)&connector;
		old.count_connectors = 1;
		ioctl(fd, DRM_IOCTL_MODE_SETCRTC, &old);
	}
fail_map:
	munmap(pixels, dumb.size);
fail:
	alarm(0);
	close(fd);
	return 1;
}
