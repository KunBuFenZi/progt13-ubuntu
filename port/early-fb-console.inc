/* SPDX-License-Identifier: GPL-2.0-only */
/* Included by EFI earlycon to reuse its mapping and bitmap-font helpers.
 * This is a temporary inherited-scanout console, not a native panel driver.
 */
#include <asm/sysreg.h>
#include <generated/utsrelease.h>

static unsigned int tb378fb_scale, tb378fb_log_top;
static unsigned int tb378fb_rows, tb378fb_hold_row;
static bool tb378fb_held;

static void tb378fb_scaled_char(u32 *dst, unsigned char c, unsigned int h)
{
	unsigned int x, repeat, bytes = BITS_TO_BYTES(font->width);
	const u8 *src = font->data + c * font->height * bytes +
		(h / tb378fb_scale) * bytes;

	for (x = 0; x < font->width; x++) {
		u32 color = src[x / 8] & (0x80 >> (x % 8)) ? 0x00ffffff : 0;

		for (repeat = 0; repeat < tb378fb_scale; repeat++)
			*dst++ = color;
	}
}

static void tb378fb_hold(void)
{
	u64 freq = read_sysreg(cntfrq_el0);
	u64 end;

	/* Use the architectural timer: delay calibration has not run yet. */
	if (!freq || freq > 1000000000)
		return;
	isb();
	end = read_sysreg(cntvct_el0) + freq * 8;
	while ((s64)(read_sysreg(cntvct_el0) - end) < 0)
		cpu_relax();
}

static void tb378fb_write(struct console *con, const char *str, unsigned int num)
{
	const struct screen_info *si = &sysfb_primary_display.screen;
	u32 stride = si->lfb_linelength;
	u32 char_width = font->width * tb378fb_scale;
	u32 char_height = font->height * tb378fb_scale;
	unsigned int count, h, n;
	void *dst;

	while (num) {
		count = min_t(unsigned int, strnchrnul(str, num, '\n') - str,
				(si->lfb_width - efi_x) / char_width);
		for (h = 0; h < char_height; h++) {
			dst = efi_earlycon_map((efi_y + h) * stride, stride);
			if (!dst)
				return;
			if (!efi_x)
				memset(dst, 0, stride);
			for (n = 0; n < count; n++)
				tb378fb_scaled_char(dst + (efi_x + n * char_width) * 4,
						    (unsigned char)str[n], h);
			efi_earlycon_unmap(dst, stride);
		}
		str += count;
		num -= count;
		efi_x += count * char_width;
		if ((num && *str == '\n') || efi_x + char_width > si->lfb_width) {
			if (num && *str == '\n') {
				str++;
				num--;
			}
			efi_x = 0;
			efi_y += char_height;
			/* Circular rows avoid copying a 31 MB framebuffer per message. */
			if (efi_y + char_height > si->lfb_height)
				efi_y = tb378fb_log_top;
			tb378fb_rows++;
			if (tb378fb_hold_row && !tb378fb_held &&
			    tb378fb_rows >= tb378fb_hold_row) {
				tb378fb_held = true;
				tb378fb_write(con, "\n[HOLD] Paused for 8 seconds.\n",
					       sizeof("\n[HOLD] Paused for 8 seconds.\n") - 1);
				tb378fb_hold();
			}
		}
	}
}

static int __init tb378fb_setup(struct earlycon_device *device, const char *options)
{
	struct screen_info *si = &sysfb_primary_display.screen;
	bool qemu = options && !strncmp(options, "qemu", 4);
	const char *opt = options;

	if (qemu) {
		opt += 4;
		if (*opt == '-')
			opt++;
	}
	if (opt && *opt) {
		if (strncmp(opt, "hold", 4) || kstrtouint(opt + 4, 10, &tb378fb_hold_row) ||
		    !tb378fb_hold_row || tb378fb_hold_row > 4096)
			return -EINVAL;
	}
	fb_base = qemu ? 0x60000000 : 0xfc800000;
	si->orig_video_isVGA = VIDEO_TYPE_EFI;
	si->lfb_base = fb_base;
	si->ext_lfb_base = 0;
	si->lfb_width = qemu ? 1024 : 3504;
	si->lfb_height = qemu ? 768 : 2190;
	si->lfb_depth = 32;
	si->lfb_linelength = si->lfb_width * 4;
	si->lfb_size = si->lfb_linelength * si->lfb_height;
	si->red_size = si->green_size = si->blue_size = 8;
	si->red_pos = 16;
	si->green_pos = 8;
	si->blue_pos = 0;
	fb_wb = false;
	font = get_default_font(si->lfb_width, si->lfb_height, NULL, NULL);
	if (!font)
		return -ENODEV;
	tb378fb_scale = qemu ? 2 : 4;
	efi_x = 0;
	efi_y = 0;
	tb378fb_held = true;
	tb378fb_write(device->con, "TB378FC MAINLINE " UTS_RELEASE "\n",
		       sizeof("TB378FC MAINLINE " UTS_RELEASE "\n") - 1);
	tb378fb_write(device->con, "Large text / one 8-second hold\n",
		       sizeof("Large text / one 8-second hold\n") - 1);
	tb378fb_log_top = efi_y;
	tb378fb_rows = 0;
	tb378fb_held = false;
	device->con->write = tb378fb_write;
	earlycon_console = device->con;
	return 0;
}
EARLYCON_DECLARE(tb378fb, tb378fb_setup);
