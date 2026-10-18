/* SPDX-License-Identifier: GPL-2.0-only */
/* Query a real render node; this does not claim to test 3D rendering. */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <drm/drm.h>
#include <drm/msm_drm.h>

static int param(int fd, uint32_t id, uint64_t *value)
{
	struct drm_msm_param query = { .pipe=MSM_PIPE_3D0, .param=id };
	if (ioctl(fd, DRM_IOCTL_MSM_GET_PARAM, &query)) {
		printf("GPU_PARAM_FAIL id=%u errno=%d\n",id,errno);
		return -1;
	}
	*value=query.value;
	return 0;
}

int main(void)
{
	char path[64];
	uint64_t chip, gmem, frequency, first, second;
	int fd, i;
	setvbuf(stdout,NULL,_IOLBF,0);
	alarm(20);
	for (i=128;i<136;i++) {
		snprintf(path,sizeof(path),"/dev/dri/renderD%d",i);
		fd=open(path,O_RDWR|O_CLOEXEC);
		if (fd<0) continue;
		if (!param(fd,MSM_PARAM_CHIP_ID,&chip) &&
		    (uint32_t)chip==0x44050001 &&
		    !param(fd,MSM_PARAM_GMEM_SIZE,&gmem) &&
		    !param(fd,MSM_PARAM_MAX_FREQ,&frequency)) {
			printf("TB378FC_GPU_INFO node=%s chip=%#" PRIx64 " gmem=%" PRIu64 " max_freq=%" PRIu64 "\n",path,chip,gmem,frequency);
			if (!param(fd,MSM_PARAM_TIMESTAMP,&first)) {
				usleep(50000);
				if (!param(fd,MSM_PARAM_TIMESTAMP,&second))
					printf("GPU_TIMESTAMPS first=%" PRIu64 " second=%" PRIu64 " advances=%d\n",first,second,second>first);
			}
			close(fd);
			return 0;
		}
		close(fd);
	}
	fprintf(stderr,"GPU_FAIL native Adreno render node unavailable\n");
	return 1;
}
