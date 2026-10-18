// SPDX-License-Identifier: GPL-2.0-only
/*
 * Device-scoped adapter for GNOME Settings Daemon 50's generated
 * GsdDisplayConfig setter. Only gsd-power loads this library. Keep the
 * distribution daemon (battery, inhibitors and notifications) running, but
 * blank the tablet's LEDs instead of restarting its broken display link.
 * The void(pointer, gint) ABI comes from org.gnome.Mutter.DisplayConfig.xml
 * and gdbus-codegen; gint is a 32-bit int on the supported arm64 platform.
 */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

typedef struct _GsdDisplayConfig GsdDisplayConfig;

void gsd_display_config_set_power_save_mode(GsdDisplayConfig *object, int mode)
{
	struct sockaddr_un address = { .sun_family = AF_UNIX };
	struct timeval timeout = { .tv_sec = 2 };
	char request[32], reply[64];
	int fd, length;
	ssize_t received;

	(void)object;
	if (mode < 0 || mode > 3)
		return;
	fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (fd < 0)
		goto failed;
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
	setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
	strcpy(address.sun_path, "/run/tb378fc-display-power/control");
	if (connect(fd, (struct sockaddr *)&address, sizeof(address)) < 0)
		goto close_failed;
	length = snprintf(request, sizeof(request), "AUTO %d\n", mode);
	if (send(fd, request, length, MSG_NOSIGNAL) != length)
		goto close_failed;
	received = recv(fd, reply, sizeof(reply) - 1, 0);
	if (received < 3 || memcmp(reply, "OK ", 3)) {
		errno = EIO;
		goto close_failed;
	}
	close(fd);
	return;

close_failed:
	close(fd);
failed:
	/* Never fall back to a modeset that leaves the physical panel dark. */
	fprintf(stderr, "tb378fc display power: backlight request failed: %s\n",
		strerror(errno));
}
