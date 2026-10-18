// SPDX-License-Identifier: GPL-2.0-only
/*
 * Temporary early boot diagnostics for TB378FC. The first page of the
 * reserved ramoops console uses the persistent_ram_buffer wire format,
 * with ECC disabled, so Android can recover it after a warm reboot.
 * CONFIG_PSTORE_RAM must be disabled in this diagnostic kernel: the normal
 * ramoops driver would otherwise become a second writer to the same page.
 */
#include <linux/console.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/serial_core.h>
#include <linux/sizes.h>

#define TB378RAM_SIGNATURE 0x43474244
#define TB378RAM_HEADER 12
#define TB378RAM_CAPACITY (SZ_4K - TB378RAM_HEADER)

static void __iomem *tb378ram_base;
static u32 tb378ram_start;
static u32 tb378ram_size;

static void tb378ram_write(struct console *con, const char *text, unsigned int count)
{
	u32 chunk;

	while (count) {
		chunk = min_t(u32, count, TB378RAM_CAPACITY - tb378ram_start);
		memcpy_toio(tb378ram_base + TB378RAM_HEADER + tb378ram_start,
			    text, chunk);
		tb378ram_start = (tb378ram_start + chunk) % TB378RAM_CAPACITY;
		tb378ram_size = min_t(u32, TB378RAM_CAPACITY, tb378ram_size + chunk);
		text += chunk;
		count -= chunk;
	}
	wmb();
	writel(tb378ram_start, tb378ram_base + 4);
	writel(tb378ram_size, tb378ram_base + 8);
}

static int __init tb378ram_setup(struct earlycon_device *device, const char *options)
{
	if (IS_ENABLED(CONFIG_PSTORE_RAM))
		return -EBUSY;
	/* Target RAM console, or the reserved QEMU test address. */
	if (device->port.mapbase != 0xc2000000 &&
	    device->port.mapbase != 0x60000000)
		return -EINVAL;
	if (!device->port.membase)
		return -ENODEV;
	tb378ram_base = device->port.membase;
	writel(TB378RAM_SIGNATURE, tb378ram_base);
	writel(0, tb378ram_base + 4);
	writel(0, tb378ram_base + 8);
	device->con->write = tb378ram_write;
	return 0;
}
EARLYCON_DECLARE(tb378ram, tb378ram_setup);
