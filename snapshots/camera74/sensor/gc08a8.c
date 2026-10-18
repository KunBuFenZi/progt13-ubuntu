// SPDX-License-Identifier: GPL-2.0-only
/* GalaxyCore GC08A8, 19.2 MHz input, four-lane RAW10. */

#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/module.h>
#include <linux/pm_runtime.h>
#include <linux/regulator/consumer.h>

#include <media/v4l2-cci.h>
#include <media/v4l2-ctrls.h>
#include <media/v4l2-fwnode.h>
#include <media/v4l2-subdev.h>

#define GC08A8_WIDTH 3264
#define GC08A8_HEIGHT 2448
#define GC08A8_HTS 3652
#define GC08A8_VTS 2548
#define GC08A8_EXPOSURE_MAX (GC08A8_VTS - 16)
#define GC08A8_CODE MEDIA_BUS_FMT_SRGGB10_1X10
#define GC08A8_PIXEL_RATE 281600000

static const s64 gc08a8_link_freq[] = { 336000000 };
static const char * const gc08a8_supply_names[] = { "dovdd", "dvdd", "avdd" };

struct gc08a8 {
	struct v4l2_subdev sd;
	struct media_pad pad;
	struct v4l2_ctrl_handler ctrls;
	struct regmap *regmap;
	struct clk *xclk;
	struct gpio_desc *reset;
	struct regulator_bulk_data supplies[ARRAY_SIZE(gc08a8_supply_names)];
	bool streaming;
};

static struct gc08a8 *to_gc08a8(struct v4l2_subdev *sd)
{
	return container_of(sd, struct gc08a8, sd);
}

static const struct cci_reg_sequence gc08a8_init_regs[] = {
	{ CCI_REG8(0x031c), 0x60 },
	{ CCI_REG8(0x0337), 0x03 },
	{ CCI_REG8(0x0335), 0x51 },
	{ CCI_REG8(0x0336), 0x69 },
	{ CCI_REG8(0x0383), 0xbb },
	{ CCI_REG8(0x031a), 0x00 },
	{ CCI_REG8(0x0321), 0x10 },
	{ CCI_REG8(0x0327), 0x03 },
	{ CCI_REG8(0x0325), 0x40 },
	{ CCI_REG8(0x0326), 0x2c },
	{ CCI_REG8(0x0314), 0x11 },
	{ CCI_REG8(0x0315), 0xd6 },
	{ CCI_REG8(0x0316), 0x01 },
	{ CCI_REG8(0x0334), 0x40 },
	{ CCI_REG8(0x0324), 0x42 },
	{ CCI_REG8(0x031c), 0x00 },
	{ CCI_REG8(0x031c), 0x9f },
	{ CCI_REG8(0x039a), 0x43 },
	{ CCI_REG8(0x0084), 0x30 },
	{ CCI_REG8(0x02b3), 0x08 },
	{ CCI_REG8(0x0057), 0x0c },
	{ CCI_REG8(0x05c3), 0x50 },
	{ CCI_REG8(0x0311), 0x90 },
	{ CCI_REG8(0x05a0), 0x02 },
	{ CCI_REG8(0x0074), 0x0a },
	{ CCI_REG8(0x0059), 0x11 },
	{ CCI_REG8(0x0070), 0x05 },
	{ CCI_REG8(0x0101), 0x00 },
	{ CCI_REG8(0x0344), 0x00 },
	{ CCI_REG8(0x0345), 0x06 },
	{ CCI_REG8(0x0346), 0x00 },
	{ CCI_REG8(0x0347), 0x04 },
	{ CCI_REG8(0x0348), 0x0c },
	{ CCI_REG8(0x0349), 0xd0 },
	{ CCI_REG8(0x034a), 0x09 },
	{ CCI_REG8(0x034b), 0x9c },
	{ CCI_REG8(0x0202), 0x09 },
	{ CCI_REG8(0x0203), 0x08 },
	{ CCI_REG8(0x0340), 0x09 },
	{ CCI_REG8(0x0341), 0xf4 },
	{ CCI_REG8(0x0342), 0x07 },
	{ CCI_REG8(0x0343), 0x22 },
	{ CCI_REG8(0x0219), 0x05 },
	{ CCI_REG8(0x0226), 0x00 },
	{ CCI_REG8(0x0227), 0x28 },
	{ CCI_REG8(0x0e0a), 0x00 },
	{ CCI_REG8(0x0e0b), 0x00 },
	{ CCI_REG8(0x0e24), 0x04 },
	{ CCI_REG8(0x0e25), 0x04 },
	{ CCI_REG8(0x0e26), 0x00 },
	{ CCI_REG8(0x0e27), 0x10 },
	{ CCI_REG8(0x0e01), 0x74 },
	{ CCI_REG8(0x0e03), 0x47 },
	{ CCI_REG8(0x0e04), 0x33 },
	{ CCI_REG8(0x0e05), 0x44 },
	{ CCI_REG8(0x0e06), 0x44 },
	{ CCI_REG8(0x0e0c), 0x1e },
	{ CCI_REG8(0x0e17), 0x3a },
	{ CCI_REG8(0x0e18), 0x3c },
	{ CCI_REG8(0x0e19), 0x40 },
	{ CCI_REG8(0x0e1a), 0x42 },
	{ CCI_REG8(0x0e28), 0x21 },
	{ CCI_REG8(0x0e2b), 0x68 },
	{ CCI_REG8(0x0e2c), 0x0d },
	{ CCI_REG8(0x0e2d), 0x08 },
	{ CCI_REG8(0x0e34), 0xf4 },
	{ CCI_REG8(0x0e35), 0x44 },
	{ CCI_REG8(0x0e36), 0x07 },
	{ CCI_REG8(0x0e38), 0x39 },
	{ CCI_REG8(0x0210), 0x13 },
	{ CCI_REG8(0x0218), 0x00 },
	{ CCI_REG8(0x0241), 0x88 },
	{ CCI_REG8(0x0e32), 0x00 },
	{ CCI_REG8(0x0e33), 0x18 },
	{ CCI_REG8(0x0e42), 0x03 },
	{ CCI_REG8(0x0e43), 0x80 },
	{ CCI_REG8(0x0e44), 0x04 },
	{ CCI_REG8(0x0e45), 0x00 },
	{ CCI_REG8(0x0e4f), 0x04 },
	{ CCI_REG8(0x057a), 0x20 },
	{ CCI_REG8(0x0381), 0x7c },
	{ CCI_REG8(0x0382), 0x9b },
	{ CCI_REG8(0x0384), 0xfb },
	{ CCI_REG8(0x0389), 0x38 },
	{ CCI_REG8(0x038a), 0x03 },
	{ CCI_REG8(0x0390), 0x6a },
	{ CCI_REG8(0x0391), 0x0f },
	{ CCI_REG8(0x0392), 0x60 },
	{ CCI_REG8(0x0393), 0xc1 },
	{ CCI_REG8(0x0396), 0x3f },
	{ CCI_REG8(0x0398), 0x22 },
	{ CCI_REG8(0x031c), 0x80 },
	{ CCI_REG8(0x03fe), 0x10 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x031c), 0x9f },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x031c), 0x80 },
	{ CCI_REG8(0x03fe), 0x10 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x031c), 0x9f },
	{ CCI_REG8(0x0360), 0x01 },
	{ CCI_REG8(0x0360), 0x00 },
	{ CCI_REG8(0x0316), 0x09 },
	{ CCI_REG8(0x0a67), 0x80 },
	{ CCI_REG8(0x0313), 0x00 },
	{ CCI_REG8(0x0a53), 0x0e },
	{ CCI_REG8(0x0a65), 0x17 },
	{ CCI_REG8(0x0a68), 0xa1 },
	{ CCI_REG8(0x0a58), 0x00 },
	{ CCI_REG8(0x0ace), 0x0c },
	{ CCI_REG8(0x00a4), 0x00 },
	{ CCI_REG8(0x00a5), 0x01 },
	{ CCI_REG8(0x00a7), 0x09 },
	{ CCI_REG8(0x00a8), 0x9c },
	{ CCI_REG8(0x00a9), 0x0c },
	{ CCI_REG8(0x00aa), 0xd0 },
	{ CCI_REG8(0x0a8a), 0x00 },
	{ CCI_REG8(0x0a8b), 0xe0 },
	{ CCI_REG8(0x0a8c), 0x13 },
	{ CCI_REG8(0x0a8d), 0xe8 },
	{ CCI_REG8(0x0a90), 0x0a },
	{ CCI_REG8(0x0a91), 0x10 },
	{ CCI_REG8(0x0a92), 0xf8 },
	{ CCI_REG8(0x0a71), 0xf2 },
	{ CCI_REG8(0x0a72), 0x12 },
	{ CCI_REG8(0x0a73), 0x64 },
	{ CCI_REG8(0x0a75), 0x41 },
	{ CCI_REG8(0x0a70), 0x07 },
	{ CCI_REG8(0x0313), 0x80 },
	{ CCI_REG8(0x00a0), 0x01 },
	{ CCI_REG8(0x0080), 0xd2 },
	{ CCI_REG8(0x0081), 0x3f },
	{ CCI_REG8(0x0087), 0x51 },
	{ CCI_REG8(0x0089), 0x03 },
	{ CCI_REG8(0x009b), 0x40 },
	{ CCI_REG8(0x0096), 0x81 },
	{ CCI_REG8(0x0097), 0x08 },
	{ CCI_REG8(0x05a0), 0x82 },
	{ CCI_REG8(0x05ac), 0x00 },
	{ CCI_REG8(0x05ad), 0x01 },
	{ CCI_REG8(0x05ae), 0x00 },
	{ CCI_REG8(0x0800), 0x0a },
	{ CCI_REG8(0x0801), 0x14 },
	{ CCI_REG8(0x0802), 0x28 },
	{ CCI_REG8(0x0803), 0x34 },
	{ CCI_REG8(0x0804), 0x0e },
	{ CCI_REG8(0x0805), 0x33 },
	{ CCI_REG8(0x0806), 0x03 },
	{ CCI_REG8(0x0807), 0x8a },
	{ CCI_REG8(0x0808), 0x3e },
	{ CCI_REG8(0x0809), 0x00 },
	{ CCI_REG8(0x080a), 0x28 },
	{ CCI_REG8(0x080b), 0x03 },
	{ CCI_REG8(0x080c), 0x1d },
	{ CCI_REG8(0x080d), 0x03 },
	{ CCI_REG8(0x080e), 0x16 },
	{ CCI_REG8(0x080f), 0x03 },
	{ CCI_REG8(0x0810), 0x10 },
	{ CCI_REG8(0x0811), 0x03 },
	{ CCI_REG8(0x0812), 0x00 },
	{ CCI_REG8(0x0813), 0x00 },
	{ CCI_REG8(0x0814), 0x01 },
	{ CCI_REG8(0x0815), 0x00 },
	{ CCI_REG8(0x0816), 0x01 },
	{ CCI_REG8(0x0817), 0x00 },
	{ CCI_REG8(0x0818), 0x00 },
	{ CCI_REG8(0x0819), 0x0a },
	{ CCI_REG8(0x081a), 0x01 },
	{ CCI_REG8(0x081b), 0x6c },
	{ CCI_REG8(0x081c), 0x00 },
	{ CCI_REG8(0x081d), 0x0b },
	{ CCI_REG8(0x081e), 0x02 },
	{ CCI_REG8(0x081f), 0x00 },
	{ CCI_REG8(0x0820), 0x00 },
	{ CCI_REG8(0x0821), 0x0c },
	{ CCI_REG8(0x0822), 0x02 },
	{ CCI_REG8(0x0823), 0xd9 },
	{ CCI_REG8(0x0824), 0x00 },
	{ CCI_REG8(0x0825), 0x0d },
	{ CCI_REG8(0x0826), 0x03 },
	{ CCI_REG8(0x0827), 0xf0 },
	{ CCI_REG8(0x0828), 0x00 },
	{ CCI_REG8(0x0829), 0x0e },
	{ CCI_REG8(0x082a), 0x05 },
	{ CCI_REG8(0x082b), 0x94 },
	{ CCI_REG8(0x082c), 0x09 },
	{ CCI_REG8(0x082d), 0x6e },
	{ CCI_REG8(0x082e), 0x07 },
	{ CCI_REG8(0x082f), 0xe6 },
	{ CCI_REG8(0x0830), 0x10 },
	{ CCI_REG8(0x0831), 0x0e },
	{ CCI_REG8(0x0832), 0x0b },
	{ CCI_REG8(0x0833), 0x2c },
	{ CCI_REG8(0x0834), 0x14 },
	{ CCI_REG8(0x0835), 0xae },
	{ CCI_REG8(0x0836), 0x0f },
	{ CCI_REG8(0x0837), 0xc4 },
	{ CCI_REG8(0x0838), 0x18 },
	{ CCI_REG8(0x0839), 0x0e },
	{ CCI_REG8(0x05ac), 0x01 },
	{ CCI_REG8(0x059a), 0x00 },
	{ CCI_REG8(0x059b), 0x00 },
	{ CCI_REG8(0x059c), 0x01 },
	{ CCI_REG8(0x0598), 0x00 },
	{ CCI_REG8(0x0597), 0x14 },
	{ CCI_REG8(0x05ab), 0x09 },
	{ CCI_REG8(0x05a4), 0x02 },
	{ CCI_REG8(0x05a3), 0x05 },
	{ CCI_REG8(0x05a0), 0xc2 },
	{ CCI_REG8(0x0207), 0xc4 },
	{ CCI_REG8(0x0208), 0x01 },
	{ CCI_REG8(0x0209), 0x78 },
	{ CCI_REG8(0x0204), 0x04 },
	{ CCI_REG8(0x0205), 0x00 },
	{ CCI_REG8(0x0040), 0x22 },
	{ CCI_REG8(0x0041), 0x20 },
	{ CCI_REG8(0x0043), 0x10 },
	{ CCI_REG8(0x0044), 0x00 },
	{ CCI_REG8(0x0046), 0x08 },
	{ CCI_REG8(0x0047), 0xf0 },
	{ CCI_REG8(0x0048), 0x0f },
	{ CCI_REG8(0x004b), 0x0f },
	{ CCI_REG8(0x004c), 0x00 },
	{ CCI_REG8(0x0050), 0x5c },
	{ CCI_REG8(0x0051), 0x44 },
	{ CCI_REG8(0x005b), 0x03 },
	{ CCI_REG8(0x00c0), 0x00 },
	{ CCI_REG8(0x00c1), 0x80 },
	{ CCI_REG8(0x00c2), 0x31 },
	{ CCI_REG8(0x00c3), 0x00 },
	{ CCI_REG8(0x0460), 0x04 },
	{ CCI_REG8(0x0462), 0x08 },
	{ CCI_REG8(0x0464), 0x0e },
	{ CCI_REG8(0x0466), 0x0a },
	{ CCI_REG8(0x0468), 0x12 },
	{ CCI_REG8(0x046a), 0x12 },
	{ CCI_REG8(0x046c), 0x10 },
	{ CCI_REG8(0x046e), 0x0c },
	{ CCI_REG8(0x0461), 0x03 },
	{ CCI_REG8(0x0463), 0x03 },
	{ CCI_REG8(0x0465), 0x03 },
	{ CCI_REG8(0x0467), 0x03 },
	{ CCI_REG8(0x0469), 0x04 },
	{ CCI_REG8(0x046b), 0x04 },
	{ CCI_REG8(0x046d), 0x04 },
	{ CCI_REG8(0x046f), 0x04 },
	{ CCI_REG8(0x0470), 0x04 },
	{ CCI_REG8(0x0472), 0x10 },
	{ CCI_REG8(0x0474), 0x26 },
	{ CCI_REG8(0x0476), 0x38 },
	{ CCI_REG8(0x0478), 0x20 },
	{ CCI_REG8(0x047a), 0x30 },
	{ CCI_REG8(0x047c), 0x38 },
	{ CCI_REG8(0x047e), 0x60 },
	{ CCI_REG8(0x0471), 0x05 },
	{ CCI_REG8(0x0473), 0x05 },
	{ CCI_REG8(0x0475), 0x05 },
	{ CCI_REG8(0x0477), 0x05 },
	{ CCI_REG8(0x0479), 0x04 },
	{ CCI_REG8(0x047b), 0x04 },
	{ CCI_REG8(0x047d), 0x04 },
	{ CCI_REG8(0x047f), 0x04 },
};

static const struct cci_reg_sequence gc08a8_3264x2448_regs[] = {
	{ CCI_REG8(0x031c), 0x60 },
	{ CCI_REG8(0x0337), 0x03 },
	{ CCI_REG8(0x0335), 0x51 },
	{ CCI_REG8(0x0336), 0x69 },
	{ CCI_REG8(0x0383), 0xbb },
	{ CCI_REG8(0x031a), 0x00 },
	{ CCI_REG8(0x0321), 0x10 },
	{ CCI_REG8(0x0327), 0x03 },
	{ CCI_REG8(0x0325), 0x40 },
	{ CCI_REG8(0x0326), 0x2c },
	{ CCI_REG8(0x0314), 0x11 },
	{ CCI_REG8(0x0315), 0xd6 },
	{ CCI_REG8(0x0316), 0x01 },
	{ CCI_REG8(0x0334), 0x40 },
	{ CCI_REG8(0x0324), 0x42 },
	{ CCI_REG8(0x031c), 0x00 },
	{ CCI_REG8(0x031c), 0x9f },
	{ CCI_REG8(0x0344), 0x00 },
	{ CCI_REG8(0x0345), 0x06 },
	{ CCI_REG8(0x0346), 0x00 },
	{ CCI_REG8(0x0347), 0x04 },
	{ CCI_REG8(0x0348), 0x0c },
	{ CCI_REG8(0x0349), 0xd0 },
	{ CCI_REG8(0x034a), 0x09 },
	{ CCI_REG8(0x034b), 0x9c },
	{ CCI_REG8(0x0202), 0x09 },
	{ CCI_REG8(0x0203), 0x08 },
	{ CCI_REG8(0x0340), 0x09 },
	{ CCI_REG8(0x0341), 0xf4 },
	{ CCI_REG8(0x0342), 0x07 },
	{ CCI_REG8(0x0343), 0x22 },
	{ CCI_REG8(0x0226), 0x00 },
	{ CCI_REG8(0x0227), 0x28 },
	{ CCI_REG8(0x0e38), 0x39 },
	{ CCI_REG8(0x0210), 0x13 },
	{ CCI_REG8(0x0218), 0x00 },
	{ CCI_REG8(0x0241), 0x88 },
	{ CCI_REG8(0x0392), 0x60 },
	{ CCI_REG8(0x031c), 0x80 },
	{ CCI_REG8(0x03fe), 0x10 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x031c), 0x9f },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x031c), 0x80 },
	{ CCI_REG8(0x03fe), 0x10 },
	{ CCI_REG8(0x03fe), 0x00 },
	{ CCI_REG8(0x031c), 0x9f },
	{ CCI_REG8(0x00a2), 0x00 },
	{ CCI_REG8(0x00a3), 0x00 },
	{ CCI_REG8(0x00ab), 0x00 },
	{ CCI_REG8(0x00ac), 0x00 },
	{ CCI_REG8(0x05a0), 0x82 },
	{ CCI_REG8(0x05ac), 0x00 },
	{ CCI_REG8(0x05ad), 0x01 },
	{ CCI_REG8(0x05ae), 0x00 },
	{ CCI_REG8(0x0800), 0x0a },
	{ CCI_REG8(0x0801), 0x14 },
	{ CCI_REG8(0x0802), 0x28 },
	{ CCI_REG8(0x0803), 0x34 },
	{ CCI_REG8(0x0804), 0x0e },
	{ CCI_REG8(0x0805), 0x33 },
	{ CCI_REG8(0x0806), 0x03 },
	{ CCI_REG8(0x0807), 0x8a },
	{ CCI_REG8(0x0808), 0x3e },
	{ CCI_REG8(0x0809), 0x00 },
	{ CCI_REG8(0x080a), 0x28 },
	{ CCI_REG8(0x080b), 0x03 },
	{ CCI_REG8(0x080c), 0x1d },
	{ CCI_REG8(0x080d), 0x03 },
	{ CCI_REG8(0x080e), 0x16 },
	{ CCI_REG8(0x080f), 0x03 },
	{ CCI_REG8(0x0810), 0x10 },
	{ CCI_REG8(0x0811), 0x03 },
	{ CCI_REG8(0x0812), 0x00 },
	{ CCI_REG8(0x0813), 0x00 },
	{ CCI_REG8(0x0814), 0x01 },
	{ CCI_REG8(0x0815), 0x00 },
	{ CCI_REG8(0x0816), 0x01 },
	{ CCI_REG8(0x0817), 0x00 },
	{ CCI_REG8(0x0818), 0x00 },
	{ CCI_REG8(0x0819), 0x0a },
	{ CCI_REG8(0x081a), 0x01 },
	{ CCI_REG8(0x081b), 0x6c },
	{ CCI_REG8(0x081c), 0x00 },
	{ CCI_REG8(0x081d), 0x0b },
	{ CCI_REG8(0x081e), 0x02 },
	{ CCI_REG8(0x081f), 0x00 },
	{ CCI_REG8(0x0820), 0x00 },
	{ CCI_REG8(0x0821), 0x0c },
	{ CCI_REG8(0x0822), 0x02 },
	{ CCI_REG8(0x0823), 0xd9 },
	{ CCI_REG8(0x0824), 0x00 },
	{ CCI_REG8(0x0825), 0x0d },
	{ CCI_REG8(0x0826), 0x03 },
	{ CCI_REG8(0x0827), 0xf0 },
	{ CCI_REG8(0x0828), 0x00 },
	{ CCI_REG8(0x0829), 0x0e },
	{ CCI_REG8(0x082a), 0x05 },
	{ CCI_REG8(0x082b), 0x94 },
	{ CCI_REG8(0x082c), 0x09 },
	{ CCI_REG8(0x082d), 0x6e },
	{ CCI_REG8(0x082e), 0x07 },
	{ CCI_REG8(0x082f), 0xe6 },
	{ CCI_REG8(0x0830), 0x10 },
	{ CCI_REG8(0x0831), 0x0e },
	{ CCI_REG8(0x0832), 0x0b },
	{ CCI_REG8(0x0833), 0x2c },
	{ CCI_REG8(0x0834), 0x14 },
	{ CCI_REG8(0x0835), 0xae },
	{ CCI_REG8(0x0836), 0x0f },
	{ CCI_REG8(0x0837), 0xc4 },
	{ CCI_REG8(0x0838), 0x18 },
	{ CCI_REG8(0x0839), 0x0e },
	{ CCI_REG8(0x05ac), 0x01 },
	{ CCI_REG8(0x059a), 0x00 },
	{ CCI_REG8(0x059b), 0x00 },
	{ CCI_REG8(0x059c), 0x01 },
	{ CCI_REG8(0x0598), 0x00 },
	{ CCI_REG8(0x0597), 0x14 },
	{ CCI_REG8(0x05ab), 0x09 },
	{ CCI_REG8(0x05a4), 0x02 },
	{ CCI_REG8(0x05a3), 0x05 },
	{ CCI_REG8(0x05a0), 0xc2 },
	{ CCI_REG8(0x0207), 0xc4 },
	{ CCI_REG8(0x0204), 0x04 },
	{ CCI_REG8(0x0205), 0x00 },
	{ CCI_REG8(0x0050), 0x5c },
	{ CCI_REG8(0x0051), 0x44 },
	{ CCI_REG8(0x009a), 0x00 },
	{ CCI_REG8(0x0351), 0x00 },
	{ CCI_REG8(0x0352), 0x06 },
	{ CCI_REG8(0x0353), 0x00 },
	{ CCI_REG8(0x0354), 0x08 },
	{ CCI_REG8(0x034c), 0x0c },
	{ CCI_REG8(0x034d), 0xc0 },
	{ CCI_REG8(0x034e), 0x09 },
	{ CCI_REG8(0x034f), 0x90 },
	{ CCI_REG8(0x0114), 0x03 },
	{ CCI_REG8(0x0180), 0x65 },
	{ CCI_REG8(0x0181), 0xf0 },
	{ CCI_REG8(0x0185), 0x01 },
	{ CCI_REG8(0x0115), 0x30 },
	{ CCI_REG8(0x011b), 0x12 },
	{ CCI_REG8(0x011c), 0x12 },
	{ CCI_REG8(0x0121), 0x06 },
	{ CCI_REG8(0x0122), 0x06 },
	{ CCI_REG8(0x0123), 0x15 },
	{ CCI_REG8(0x0124), 0x01 },
	{ CCI_REG8(0x0125), 0x13 },
	{ CCI_REG8(0x0126), 0x08 },
	{ CCI_REG8(0x0129), 0x06 },
	{ CCI_REG8(0x012a), 0x08 },
	{ CCI_REG8(0x012b), 0x08 },
	{ CCI_REG8(0x0a73), 0x60 },
	{ CCI_REG8(0x0a70), 0x11 },
	{ CCI_REG8(0x0313), 0x80 },
	{ CCI_REG8(0x0aff), 0x00 },
	{ CCI_REG8(0x0aff), 0x00 },
	{ CCI_REG8(0x0aff), 0x00 },
	{ CCI_REG8(0x0aff), 0x00 },
	{ CCI_REG8(0x0aff), 0x00 },
	{ CCI_REG8(0x0aff), 0x00 },
	{ CCI_REG8(0x0aff), 0x00 },
	{ CCI_REG8(0x0aff), 0x00 },
	{ CCI_REG8(0x0a70), 0x00 },
	{ CCI_REG8(0x00a4), 0x80 },
	{ CCI_REG8(0x0316), 0x01 },
	{ CCI_REG8(0x0a67), 0x00 },
	{ CCI_REG8(0x0084), 0x10 },
	{ CCI_REG8(0x0102), 0x09 },
};

static int gc08a8_power_on(struct device *dev)
{
	struct gc08a8 *sensor = to_gc08a8(dev_get_drvdata(dev));
	int i, ret;

	gpiod_set_value_cansleep(sensor->reset, 1);
	fsleep(1000);
	for (i = 0; i < ARRAY_SIZE(sensor->supplies); i++) {
		ret = regulator_enable(sensor->supplies[i].consumer);
		if (ret)
			goto disable_supplies;
		fsleep(1000);
	}

	ret = clk_prepare_enable(sensor->xclk);
	if (ret)
		goto disable_supplies;
	fsleep(10000);
	gpiod_set_value_cansleep(sensor->reset, 0);
	fsleep(3000);
	return 0;

disable_supplies:
	while (i--) {
		regulator_disable(sensor->supplies[i].consumer);
		fsleep(1000);
	}
	return ret;
}

static int gc08a8_power_off(struct device *dev)
{
	struct gc08a8 *sensor = to_gc08a8(dev_get_drvdata(dev));
	int i;

	gpiod_set_value_cansleep(sensor->reset, 1);
	fsleep(3000);
	clk_disable_unprepare(sensor->xclk);
	fsleep(10000);
	for (i = ARRAY_SIZE(sensor->supplies) - 1; i >= 0; i--) {
		regulator_disable(sensor->supplies[i].consumer);
		fsleep(1000);
	}
	return 0;
}

static int gc08a8_set_ctrl(struct v4l2_ctrl *ctrl)
{
	struct gc08a8 *sensor = container_of(ctrl->handler, struct gc08a8, ctrls);
	struct device *dev = sensor->sd.dev;
	u16 reg;
	int ret = 0, release;

	switch (ctrl->id) {
	case V4L2_CID_EXPOSURE:
		reg = 0x0202;
		break;
	case V4L2_CID_ANALOGUE_GAIN:
		reg = 0x0204;
		break;
	default:
		return 0;
	}

	ret = pm_runtime_get_if_in_use(dev);
	if (ret <= 0)
		return ret;
	ret = 0;

	cci_write(sensor->regmap, CCI_REG8(0x0104), 1, &ret);
	cci_write(sensor->regmap, CCI_REG8(reg), ctrl->val >> 8, &ret);
	cci_write(sensor->regmap, CCI_REG8(reg + 1), ctrl->val & 0xff, &ret);
	/* Release group hold even when a control write failed. */
	release = cci_write(sensor->regmap, CCI_REG8(0x0104), 0, NULL);
	pm_runtime_put(dev);
	return ret ? ret : release;
}

static const struct v4l2_ctrl_ops gc08a8_ctrl_ops = {
	.s_ctrl = gc08a8_set_ctrl,
};

static int gc08a8_init_controls(struct gc08a8 *sensor)
{
	struct v4l2_ctrl_handler *hdl = &sensor->ctrls;
	struct v4l2_fwnode_device_properties props;
	struct v4l2_ctrl *ctrl;
	int ret;

	ret = v4l2_fwnode_device_parse(sensor->sd.dev, &props);
	if (ret)
		return ret;
	v4l2_ctrl_handler_init(hdl, 8);
	ctrl = v4l2_ctrl_new_int_menu(hdl, NULL, V4L2_CID_LINK_FREQ, 0, 0,
				      gc08a8_link_freq);
	if (ctrl)
		ctrl->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	v4l2_ctrl_new_std(hdl, NULL, V4L2_CID_PIXEL_RATE,
			  GC08A8_PIXEL_RATE, GC08A8_PIXEL_RATE, 1, GC08A8_PIXEL_RATE);
	ctrl = v4l2_ctrl_new_std(hdl, NULL, V4L2_CID_HBLANK,
				 GC08A8_HTS - GC08A8_WIDTH, GC08A8_HTS - GC08A8_WIDTH,
				 1, GC08A8_HTS - GC08A8_WIDTH);
	if (ctrl)
		ctrl->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	ctrl = v4l2_ctrl_new_std(hdl, NULL, V4L2_CID_VBLANK,
				 GC08A8_VTS - GC08A8_HEIGHT, GC08A8_VTS - GC08A8_HEIGHT,
				 1, GC08A8_VTS - GC08A8_HEIGHT);
	if (ctrl)
		ctrl->flags |= V4L2_CTRL_FLAG_READ_ONLY;
	v4l2_ctrl_new_std(hdl, &gc08a8_ctrl_ops, V4L2_CID_EXPOSURE,
			  4, GC08A8_EXPOSURE_MAX, 1, 0x0904);
	v4l2_ctrl_new_std(hdl, &gc08a8_ctrl_ops, V4L2_CID_ANALOGUE_GAIN,
			  1024, 16384, 1, 1024);
	v4l2_ctrl_new_fwnode_properties(hdl, &gc08a8_ctrl_ops, &props);
	if (hdl->error) {
		ret = hdl->error;
		v4l2_ctrl_handler_free(hdl);
		return ret;
	}
	sensor->sd.ctrl_handler = hdl;
	return 0;
}

static int gc08a8_set_fmt(struct v4l2_subdev *sd,
			  struct v4l2_subdev_state *state,
			  struct v4l2_subdev_format *format)
{
	struct gc08a8 *sensor = to_gc08a8(sd);

	if (format->pad)
		return -EINVAL;
	if (format->which == V4L2_SUBDEV_FORMAT_ACTIVE && sensor->streaming)
		return -EBUSY;

	format->format = (struct v4l2_mbus_framefmt) {
		.width = GC08A8_WIDTH,
		.height = GC08A8_HEIGHT,
		.code = GC08A8_CODE,
		.field = V4L2_FIELD_NONE,
		.colorspace = V4L2_COLORSPACE_RAW,
		.ycbcr_enc = V4L2_YCBCR_ENC_DEFAULT,
		.quantization = V4L2_QUANTIZATION_FULL_RANGE,
		.xfer_func = V4L2_XFER_FUNC_NONE,
	};
	*v4l2_subdev_state_get_format(state, 0) = format->format;
	return 0;
}

static int gc08a8_init_state(struct v4l2_subdev *sd,
			     struct v4l2_subdev_state *state)
{
	struct v4l2_subdev_format format = { .which = V4L2_SUBDEV_FORMAT_TRY };

	return gc08a8_set_fmt(sd, state, &format);
}

static int gc08a8_enum_code(struct v4l2_subdev *sd,
			    struct v4l2_subdev_state *state,
			    struct v4l2_subdev_mbus_code_enum *code)
{
	if (code->pad || code->index)
		return -EINVAL;
	code->code = GC08A8_CODE;
	return 0;
}

static int gc08a8_enum_size(struct v4l2_subdev *sd,
			    struct v4l2_subdev_state *state,
			    struct v4l2_subdev_frame_size_enum *size)
{
	if (size->pad || size->index || size->code != GC08A8_CODE)
		return -EINVAL;
	size->min_width = GC08A8_WIDTH;
	size->max_width = GC08A8_WIDTH;
	size->min_height = GC08A8_HEIGHT;
	size->max_height = GC08A8_HEIGHT;
	return 0;
}

static int gc08a8_get_selection(struct v4l2_subdev *sd,
				struct v4l2_subdev_state *state,
				struct v4l2_subdev_selection *sel)
{
	if (sel->pad)
		return -EINVAL;
	switch (sel->target) {
	case V4L2_SEL_TGT_NATIVE_SIZE:
	case V4L2_SEL_TGT_CROP:
	case V4L2_SEL_TGT_CROP_DEFAULT:
	case V4L2_SEL_TGT_CROP_BOUNDS:
		sel->r = (struct v4l2_rect) {
			.width = GC08A8_WIDTH,
			.height = GC08A8_HEIGHT,
		};
		return 0;
	default:
		return -EINVAL;
	}
}

static int gc08a8_s_stream(struct v4l2_subdev *sd, int enable)
{
	struct gc08a8 *sensor = to_gc08a8(sd);
	struct v4l2_subdev_state *state;
	int ret = 0;

	state = v4l2_subdev_lock_and_get_active_state(sd);
	if (sensor->streaming == !!enable)
		goto unlock;
	if (!enable) {
		ret = cci_write(sensor->regmap, CCI_REG8(0x0100), 0, NULL);
		sensor->streaming = false;
		/* Reset and remove power even if the stream-off write failed. */
		pm_runtime_put_sync(sd->dev);
		goto unlock;
	}

	ret = pm_runtime_resume_and_get(sd->dev);
	if (ret < 0)
		goto unlock;
	cci_multi_reg_write(sensor->regmap, gc08a8_init_regs,
			    ARRAY_SIZE(gc08a8_init_regs), &ret);
	cci_multi_reg_write(sensor->regmap, gc08a8_3264x2448_regs,
			    ARRAY_SIZE(gc08a8_3264x2448_regs), &ret);
	if (!ret)
		ret = __v4l2_ctrl_handler_setup(&sensor->ctrls);
	cci_write(sensor->regmap, CCI_REG8(0x0100), 1, &ret);
	if (ret)
		pm_runtime_put_sync(sd->dev);
	else
		sensor->streaming = true;
unlock:
	v4l2_subdev_unlock_state(state);
	return ret;
}

static const struct v4l2_subdev_video_ops gc08a8_video_ops = {
	.s_stream = gc08a8_s_stream,
};

static const struct v4l2_subdev_pad_ops gc08a8_pad_ops = {
	.enum_mbus_code = gc08a8_enum_code,
	.enum_frame_size = gc08a8_enum_size,
	.get_fmt = v4l2_subdev_get_fmt,
	.set_fmt = gc08a8_set_fmt,
	.get_selection = gc08a8_get_selection,
};

static const struct v4l2_subdev_ops gc08a8_ops = {
	.video = &gc08a8_video_ops,
	.pad = &gc08a8_pad_ops,
};

static const struct v4l2_subdev_internal_ops gc08a8_internal_ops = {
	.init_state = gc08a8_init_state,
};

static int gc08a8_check_endpoint(struct device *dev)
{
	struct v4l2_fwnode_endpoint bus = { .bus_type = V4L2_MBUS_CSI2_DPHY };
	struct fwnode_handle *ep;
	unsigned long bitmap;
	int ret, i;

	ep = fwnode_graph_get_next_endpoint(dev_fwnode(dev), NULL);
	if (!ep)
		return -EINVAL;
	ret = v4l2_fwnode_endpoint_alloc_parse(ep, &bus);
	fwnode_handle_put(ep);
	if (ret)
		goto free;
	ret = -EINVAL;
	if (bus.bus.mipi_csi2.num_data_lanes != 4)
		goto free;
	for (i = 0; i < 4; i++)
		if (bus.bus.mipi_csi2.data_lanes[i] != i + 1)
			goto free;
	ret = v4l2_link_freq_to_bitmap(dev, bus.link_frequencies,
				       bus.nr_of_link_frequencies, gc08a8_link_freq,
				       ARRAY_SIZE(gc08a8_link_freq), &bitmap);
free:
	v4l2_fwnode_endpoint_free(&bus);
	return ret;
}

static int gc08a8_probe(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct gc08a8 *sensor;
	u64 id;
	int ret, i;

	ret = gc08a8_check_endpoint(dev);
	if (ret)
		return dev_err_probe(dev, ret, "Unsupported CSI-2 endpoint\n");
	sensor = devm_kzalloc(dev, sizeof(*sensor), GFP_KERNEL);
	if (!sensor)
		return -ENOMEM;
	sensor->regmap = devm_cci_regmap_init_i2c(client, 16);
	if (IS_ERR(sensor->regmap))
		return dev_err_probe(dev, PTR_ERR(sensor->regmap), "Failed to create regmap\n");
	sensor->xclk = devm_v4l2_sensor_clk_get(dev, NULL);
	if (IS_ERR(sensor->xclk))
		return dev_err_probe(dev, PTR_ERR(sensor->xclk), "Failed to get sensor clock\n");
	if (clk_get_rate(sensor->xclk) != 19200000)
		return dev_err_probe(dev, -EINVAL, "Only a 19.2 MHz input clock is supported\n");
	for (i = 0; i < ARRAY_SIZE(sensor->supplies); i++)
		sensor->supplies[i].supply = gc08a8_supply_names[i];
	ret = devm_regulator_bulk_get(dev, ARRAY_SIZE(sensor->supplies), sensor->supplies);
	if (ret)
		return dev_err_probe(dev, ret, "Failed to get supplies\n");
	sensor->reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(sensor->reset))
		return dev_err_probe(dev, PTR_ERR(sensor->reset), "Failed to get reset GPIO\n");

	v4l2_i2c_subdev_init(&sensor->sd, client, &gc08a8_ops);
	sensor->sd.internal_ops = &gc08a8_internal_ops;
	sensor->sd.flags |= V4L2_SUBDEV_FL_HAS_DEVNODE;
	sensor->sd.entity.function = MEDIA_ENT_F_CAM_SENSOR;
	sensor->pad.flags = MEDIA_PAD_FL_SOURCE;

	ret = gc08a8_power_on(dev);
	if (ret)
		return dev_err_probe(dev, ret, "Failed to power sensor\n");
	ret = cci_read(sensor->regmap, CCI_REG16(0x03f0), &id, NULL);
	gc08a8_power_off(dev);
	if (ret)
		return dev_err_probe(dev, ret, "Failed to read sensor ID\n");
	if (id != 0x08a8)
		return dev_err_probe(dev, -ENODEV, "Unexpected sensor ID: %#llx\n", id);

	dev_info(dev, "GC08A8 identity confirmed: %#llx\n", id);

	ret = gc08a8_init_controls(sensor);
	if (ret)
		return ret;
	ret = media_entity_pads_init(&sensor->sd.entity, 1, &sensor->pad);
	if (ret)
		goto free_controls;
	sensor->sd.state_lock = sensor->ctrls.lock;
	ret = v4l2_subdev_init_finalize(&sensor->sd);
	if (ret)
		goto clean_entity;

	pm_runtime_set_suspended(dev);
	pm_runtime_enable(dev);
	ret = v4l2_async_register_subdev_sensor(&sensor->sd);
	if (ret)
		goto disable_pm;
	return 0;

disable_pm:
	pm_runtime_disable(dev);
	v4l2_subdev_cleanup(&sensor->sd);
clean_entity:
	media_entity_cleanup(&sensor->sd.entity);
free_controls:
	v4l2_ctrl_handler_free(&sensor->ctrls);
	return ret;
}

static void gc08a8_remove(struct i2c_client *client)
{
	struct v4l2_subdev *sd = i2c_get_clientdata(client);
	struct gc08a8 *sensor = to_gc08a8(sd);

	v4l2_async_unregister_subdev(sd);
	pm_runtime_disable(sd->dev);
	if (!pm_runtime_status_suspended(sd->dev))
		gc08a8_power_off(sd->dev);
	pm_runtime_set_suspended(sd->dev);
	v4l2_subdev_cleanup(sd);
	media_entity_cleanup(&sd->entity);
	v4l2_ctrl_handler_free(&sensor->ctrls);
}

static int gc08a8_suspend(struct device *dev)
{
	struct v4l2_subdev *sd = dev_get_drvdata(dev);
	struct gc08a8 *sensor = to_gc08a8(sd);
	struct v4l2_subdev_state *state;
	int ret;

	state = v4l2_subdev_lock_and_get_active_state(sd);
	ret = sensor->streaming ? -EBUSY : pm_runtime_force_suspend(dev);
	v4l2_subdev_unlock_state(state);
	return ret;
}

static const struct dev_pm_ops gc08a8_pm_ops = {
	SYSTEM_SLEEP_PM_OPS(gc08a8_suspend, pm_runtime_force_resume)
	RUNTIME_PM_OPS(gc08a8_power_off, gc08a8_power_on, NULL)
};

static const struct of_device_id gc08a8_of_match[] = {
	{ .compatible = "galaxycore,gc08a8" },
	{ }
};
MODULE_DEVICE_TABLE(of, gc08a8_of_match);

static struct i2c_driver gc08a8_driver = {
	.driver = {
		.name = "gc08a8",
		.of_match_table = gc08a8_of_match,
		.pm = pm_ptr(&gc08a8_pm_ops),
	},
	.probe = gc08a8_probe,
	.remove = gc08a8_remove,
};
module_i2c_driver(gc08a8_driver);

MODULE_DESCRIPTION("GalaxyCore GC08A8 image sensor driver");
MODULE_LICENSE("GPL");
