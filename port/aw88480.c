// SPDX-License-Identifier: GPL-2.0-only
/* AW88480 / PID 0x2418 ASoC bring-up.
 * Register definitions and sequencing: Awinic AW882XX Qcom v2.0.13,
 * aw882xx_init.[ch] and aw882xx_device.c (GPL-2.0).
 * Uses this board's original Music register bins through the upstream ACF parser.
 */
#include <linux/delay.h>
#include <linux/firmware.h>
#include <linux/gpio/consumer.h>
#include <linux/i2c.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/property.h>
#include <linux/regmap.h>
#include <linux/unaligned.h>
#include <linux/workqueue.h>
#include <sound/pcm_params.h>
#include <sound/soc.h>
#include <sound/tlv.h>
#include "aw88395/aw88395_device.h"

#define AW48_ID                 0x00
#define AW48_STATUS             0x01
#define AW48_INT                0x02
#define AW48_INT_MASK           0x03
#define AW48_CTRL               0x04
#define AW48_VOLUME             0x05
#define AW48_TX                 0x08
#define AW48_VBAT               0x20
#define AW48_TEMP               0x21
#define AW48_DBG                0x25
#define AW48_LPC                0x3a
#define AW48_NOISE_GATE         0x52
#define AW48_TRIM               0x76
#define AW48_PWDN               BIT(0)
#define AW48_AMPPD              BIT(1)
#define AW48_MUTE               BIT(8)
#define AW48_ULS_MUTE           BIT(15)
#define AW48_TXEN               BIT(5)
#define AW48_DITHER             BIT(15)
#define AW48_CCO_BYPASS         BIT(13)
#define AW48_LPC_EN             BIT(8)
#define AW48_ATTENUATION        GENMASK(9, 0)
#define AW48_PLL_READY          (BIT(4) | BIT(0))
#define AW48_NO_SWS_READY       (BIT(9) | AW48_PLL_READY)
#define AW48_SWS_READY          (BIT(8) | AW48_NO_SWS_READY)
#define AW48_TRIM_LOCKED        BIT(15)
#define AW48_FAULTS             (BIT(14) | BIT(11) | BIT(5) | BIT(3) | BIT(1))
/* Bring-up ceiling until vendor excursion/thermal protection is available. */
#define AW48_GAIN_MAX           487 /* At least 6 dB below native Music. */
#define AW48_GAIN_DEFAULT       463 /* Default to 12 dB attenuation. */

struct aw88480 {
	struct aw_device aw;
	struct regmap *regmap;
	struct gpio_desc *reset;
	struct mutex lock;
	struct delayed_work start_work;
	struct delayed_work monitor_work;
	u8 *registers;
	unsigned int register_bytes;
	unsigned int channel;
	unsigned int gain;
	unsigned int native_attenuation;
	unsigned int attenuation;
	u16 dither, lpc, tx;
	bool requested, powered, running;
	int last_error;
};

static const struct regmap_config aw88480_regmap = {
	.reg_bits = 8,
	.val_bits = 16,
	.val_format_endian = REGMAP_ENDIAN_BIG,
	/* The native Music bins also program zeroes at 0x80..0x89. */
	.max_register = 0x89,
};

static int aw88480_ramp(struct aw88480 *amp, unsigned int target)
{
	int ret;

	while (amp->attenuation != target) {
		unsigned int next = amp->attenuation;

		if (next < target)
			next += min(64U, target - next);
		else
			next -= min(64U, next - target);
		ret = regmap_update_bits(amp->regmap, AW48_VOLUME,
					 AW48_ATTENUATION, next);
		if (ret)
			return ret;
		amp->attenuation = next;
		usleep_range(500, 600);
	}
	return 0;
}

static void aw88480_stop(struct aw88480 *amp)
{
	cancel_delayed_work(&amp->monitor_work);
	if (amp->powered) {
		aw88480_ramp(amp, AW48_ATTENUATION);
		regmap_update_bits(amp->regmap, AW48_CTRL,
				   AW48_MUTE | AW48_ULS_MUTE,
				   AW48_MUTE | AW48_ULS_MUTE);
		usleep_range(5000, 5100);
		regmap_update_bits(amp->regmap, AW48_TX, AW48_TXEN, 0);
		regmap_update_bits(amp->regmap, AW48_CTRL,
				   AW48_AMPPD | AW48_PWDN,
				   AW48_AMPPD | AW48_PWDN);
	}
	/* Reset also makes a failed or partial configuration unconditionally quiet. */
	gpiod_set_value_cansleep(amp->reset, 1);
	amp->powered = false;
}

static int aw88480_configure(struct aw88480 *amp)
{
	unsigned int i, trim, id;
	int ret;

	gpiod_set_value_cansleep(amp->reset, 0);
	usleep_range(2000, 2100);
	/* Early probe bus traffic disrupts display initialization on this board.
	 * Validate the real chip before any configuration writes at PCM start.
	 */
	ret = regmap_read(amp->regmap, AW48_ID, &id);
	if (ret)
		return ret;
	if (id != 0x2418)
		return dev_err_probe(amp->aw.dev, -ENODEV, "unexpected chip ID %#x\n", id);
	dev_info(amp->aw.dev, "AW88480 channel%u chip ID verified=0x%04x\n",
		 amp->channel, id);
	ret = regmap_write(amp->regmap, AW48_ID, 0x55aa);
	if (ret)
		return ret;
	usleep_range(1000, 1100);
	ret = regmap_read(amp->regmap, AW48_TRIM, &trim);
	if (ret)
		return ret;
	if (!(trim & AW48_TRIM_LOCKED))
		return -EIO;

	for (i = 0; i < amp->register_bytes; i += 4) {
		unsigned int reg = get_unaligned_le16(amp->registers + i);
		unsigned int value = get_unaligned_le16(amp->registers + i + 2);

		if (reg == AW48_CTRL)
			value |= AW48_PWDN | AW48_AMPPD | AW48_MUTE | AW48_ULS_MUTE;
		if (reg == AW48_INT_MASK)
			value = 0xffff;
		if (reg == AW48_VOLUME) {
			amp->native_attenuation = value & AW48_ATTENUATION;
			value |= AW48_ATTENUATION;
		}
		if (reg == AW48_TX) {
			amp->tx = value & AW48_TXEN;
			value &= ~AW48_TXEN;
		}
		if (reg == AW48_DBG) {
			amp->dither = value & AW48_DITHER;
			value &= ~AW48_DITHER;
		}
		if (reg == AW48_LPC) {
			amp->lpc = value & AW48_LPC_EN;
			value &= ~AW48_LPC_EN;
		}
		ret = regmap_write(amp->regmap, reg, value);
		if (ret)
			return ret;
	}
	amp->attenuation = AW48_ATTENUATION;
	return 0;
}

static int aw88480_start(struct aw88480 *amp)
{
	unsigned int status, gate, ready;
	int ret;

	ret = aw88480_configure(amp);
	if (ret)
		return ret;
	ret = regmap_update_bits(amp->regmap, AW48_CTRL, AW48_PWDN, 0);
	if (ret)
		return ret;
	ret = regmap_read_poll_timeout(amp->regmap, AW48_STATUS, status,
			(status & AW48_PLL_READY) == AW48_PLL_READY, 2000, 40000);
	if (ret)
		return ret;
	ret = regmap_update_bits(amp->regmap, AW48_CTRL, AW48_AMPPD, 0);
	if (ret)
		return ret;
	usleep_range(1000, 1100);
	ret = regmap_read(amp->regmap, AW48_NOISE_GATE, &gate);
	if (ret)
		return ret;
	ready = gate & BIT(0) ? AW48_NO_SWS_READY : AW48_SWS_READY;
	ret = regmap_read_poll_timeout(amp->regmap, AW48_STATUS, status,
			(status & ready) == ready && !(status & AW48_FAULTS), 2000, 40000);
	if (ret)
		return ret;
	/* No capture graph yet: do not drive the shared feedback data line. */
	ret = regmap_update_bits(amp->regmap, AW48_TX, AW48_TXEN, 0);
	if (ret)
		return ret;
	ret = regmap_update_bits(amp->regmap, AW48_CTRL,
				 AW48_MUTE | AW48_ULS_MUTE, 0);
	if (ret)
		return ret;
	ret = regmap_update_bits(amp->regmap, AW48_DBG, AW48_DITHER, amp->dither);
	if (ret)
		return ret;
	ret = regmap_update_bits(amp->regmap, AW48_LPC, AW48_LPC_EN, amp->lpc);
	if (ret)
		return ret;
	ret = aw88480_ramp(amp, min(1023U, amp->native_attenuation +
						2 * (511 - amp->gain)));
	if (ret)
		return ret;
	amp->powered = true;
	dev_info(amp->aw.dev, "AW88480 channel%u running status=0x%04x attenuation=%u\n",
		 amp->channel, status, amp->attenuation);
	return 0;
}

static void aw88480_monitor_work(struct work_struct *work)
{
	struct aw88480 *amp = container_of(to_delayed_work(work), struct aw88480, monitor_work);
	unsigned int status;
	int ret;

	mutex_lock(&amp->lock);
	if (!amp->powered || !amp->requested || !READ_ONCE(amp->running))
		goto out;
	ret = regmap_read(amp->regmap, AW48_STATUS, &status);
	/* Native silence detection can report zero; fault bits are always fatal. */
	if (ret || (status & AW48_FAULTS)) {
		amp->last_error = ret ?: -EIO;
		dev_err(amp->aw.dev, "AW88480 runtime fault status=0x%04x error=%d, resetting\n",
			ret ? 0 : status, amp->last_error);
		aw88480_stop(amp);
	} else {
		schedule_delayed_work(&amp->monitor_work, msecs_to_jiffies(100));
	}
out:
	mutex_unlock(&amp->lock);
}

static void aw88480_start_work(struct work_struct *work)
{
	struct aw88480 *amp = container_of(to_delayed_work(work), struct aw88480, start_work);
	int attempt, ret = -EIO;

	mutex_lock(&amp->lock);
	if (!amp->requested || !READ_ONCE(amp->running)) {
		aw88480_stop(amp);
		goto out;
	}
	if (amp->powered)
		goto out;
	for (attempt = 0; attempt < 3; attempt++) {
		if (!READ_ONCE(amp->running)) {
			ret = 0;
			break;
		}
		ret = aw88480_start(amp);
		if (!ret)
			break;
		aw88480_stop(amp);
		usleep_range(5000, 5100);
	}
	amp->last_error = ret;
	if (ret)
		dev_err(amp->aw.dev, "AW88480 start failed, stays muted: %d\n", ret);
	else if (amp->powered && READ_ONCE(amp->running))
		schedule_delayed_work(&amp->monitor_work, msecs_to_jiffies(100));
out:
	mutex_unlock(&amp->lock);
}

static int aw88480_mute(struct snd_soc_dai *dai, int mute, int stream)
{
	struct aw88480 *amp = snd_soc_component_get_drvdata(dai->component);

	if (stream != SNDRV_PCM_STREAM_PLAYBACK)
		return 0;
	if (mute) {
		cancel_delayed_work_sync(&amp->start_work);
		cancel_delayed_work_sync(&amp->monitor_work);
	}
	mutex_lock(&amp->lock);
	amp->requested = !mute;
	if (mute)
		aw88480_stop(amp);
	else if (READ_ONCE(amp->running))
		schedule_delayed_work(&amp->start_work, msecs_to_jiffies(2));
	mutex_unlock(&amp->lock);
	return 0;
}

static int aw88480_trigger(struct snd_pcm_substream *substream, int cmd,
			  struct snd_soc_dai *dai)
{
	struct aw88480 *amp = snd_soc_component_get_drvdata(dai->component);
	bool running;

	if (substream->stream != SNDRV_PCM_STREAM_PLAYBACK)
		return 0;
	switch (cmd) {
	case SNDRV_PCM_TRIGGER_START:
	case SNDRV_PCM_TRIGGER_RESUME:
	case SNDRV_PCM_TRIGGER_PAUSE_RELEASE:
		running = true;
		break;
	case SNDRV_PCM_TRIGGER_STOP:
	case SNDRV_PCM_TRIGGER_SUSPEND:
	case SNDRV_PCM_TRIGGER_PAUSE_PUSH:
		running = false;
		break;
	default:
		return -EINVAL;
	}
	/* ALSA may trigger in atomic context: all I2C/reset work stays in workqueues. */
	WRITE_ONCE(amp->running, running);
	mod_delayed_work(system_dfl_wq, &amp->start_work,
			 running ? msecs_to_jiffies(2) : 0);
	return 0;
}

static int aw88480_set_fmt(struct snd_soc_dai *dai, unsigned int fmt)
{
	/* The board firmware supplies the native DSP_B framing registers. */
	if ((fmt & SND_SOC_DAIFMT_FORMAT_MASK) != SND_SOC_DAIFMT_DSP_B)
		return -EINVAL;
	if ((fmt & SND_SOC_DAIFMT_INV_MASK) != SND_SOC_DAIFMT_NB_NF &&
	    (fmt & SND_SOC_DAIFMT_INV_MASK) != SND_SOC_DAIFMT_IB_NF)
		return -EINVAL;
	return 0;
}

static int aw88480_set_slots(struct snd_soc_dai *dai, unsigned int tx,
			    unsigned int rx, int slots, int width)
{
	struct aw88480 *amp = snd_soc_component_get_drvdata(dai->component);

	if ((slots != 4 && slots != 8) || width != 32 || amp->channel >= slots)
		return -EINVAL;
	if (rx != BIT(amp->channel) || (tx && tx != BIT(amp->channel)))
		return -EINVAL;
	return 0;
}

static const struct snd_soc_dai_ops aw88480_ops = {
	.set_fmt = aw88480_set_fmt,
	.set_tdm_slot = aw88480_set_slots,
	.mute_stream = aw88480_mute,
	.trigger = aw88480_trigger,
	.no_capture_mute = 1,
};

static struct snd_soc_dai_driver aw88480_dai = {
	.name = "aw88480-aif",
	.playback = {
		.stream_name = "Speaker Playback",
		.channels_min = 1,
		.channels_max = 8,
		.rates = SNDRV_PCM_RATE_48000,
		.formats = SNDRV_PCM_FMTBIT_S32_LE,
	},
	.ops = &aw88480_ops,
};

static int aw88480_volume_get(struct snd_kcontrol *kcontrol,
			     struct snd_ctl_elem_value *value)
{
	struct snd_soc_component *component = snd_kcontrol_chip(kcontrol);
	struct aw88480 *amp = snd_soc_component_get_drvdata(component);

	mutex_lock(&amp->lock);
	value->value.integer.value[0] = amp->gain;
	mutex_unlock(&amp->lock);
	return 0;
}

static int aw88480_volume_put(struct snd_kcontrol *kcontrol,
			     struct snd_ctl_elem_value *value)
{
	struct snd_soc_component *component = snd_kcontrol_chip(kcontrol);
	struct aw88480 *amp = snd_soc_component_get_drvdata(component);
	unsigned int gain = value->value.integer.value[0];
	int ret = 1;

	if (gain > AW48_GAIN_MAX)
		return -EINVAL;
	mutex_lock(&amp->lock);
	if (gain == amp->gain) {
		ret = 0;
		goto out;
	}
	if (amp->powered) {
		ret = aw88480_ramp(amp, min(1023U, amp->native_attenuation + 2 * (511 - gain)));
		if (ret)
			goto out;
		ret = 1;
	}
	amp->gain = gain;
out:
	mutex_unlock(&amp->lock);
	return ret;
}

static const DECLARE_TLV_DB_SCALE(aw88480_volume_tlv, -12775, 25, 0);
static const struct snd_kcontrol_new aw88480_controls[] = {
	SOC_SINGLE_EXT_TLV("Playback Volume", SND_SOC_NOPM, 0, AW48_GAIN_MAX, 0,
			   aw88480_volume_get, aw88480_volume_put, aw88480_volume_tlv),
};
static const struct snd_soc_dapm_widget aw88480_widgets[] = {
	SND_SOC_DAPM_AIF_IN("AIF_RX", "Speaker Playback", 0, SND_SOC_NOPM, 0, 0),
	SND_SOC_DAPM_OUTPUT("OUT"),
};
static const struct snd_soc_dapm_route aw88480_routes[] = {
	{ "OUT", NULL, "AIF_RX" },
};
static const struct snd_soc_component_driver aw88480_component = {
	.controls = aw88480_controls,
	.num_controls = ARRAY_SIZE(aw88480_controls),
	.dapm_widgets = aw88480_widgets,
	.num_dapm_widgets = ARRAY_SIZE(aw88480_widgets),
	.dapm_routes = aw88480_routes,
	.num_dapm_routes = ARRAY_SIZE(aw88480_routes),
};

static int aw88480_load_firmware(struct aw88480 *amp)
{
	const struct firmware *fw;
	const char *name;
	struct aw_container *cfg;
	struct aw_sec_data_desc *regs;
	unsigned int i;
	int ret;

	ret = device_property_read_string(amp->aw.dev, "firmware-name", &name);
	if (ret)
		return ret;
	ret = request_firmware(&fw, name, amp->aw.dev);
	if (ret)
		return ret;
	cfg = devm_kzalloc(amp->aw.dev, struct_size(cfg, data, fw->size), GFP_KERNEL);
	if (!cfg) {
		release_firmware(fw);
		return -ENOMEM;
	}
	cfg->len = fw->size;
	memcpy(cfg->data, fw->data, fw->size);
	release_firmware(fw);
	ret = aw88395_dev_load_acf_check(&amp->aw, cfg);
	if (ret)
		return ret;
	ret = aw88395_dev_cfg_load(&amp->aw, cfg);
	if (ret)
		return ret;
	if (amp->aw.prof_info.count != 1)
		return -EINVAL;
	regs = &amp->aw.prof_info.prof_desc[0].sec_desc[AW88395_DATA_TYPE_REG];
	if (!regs->len || regs->len % 4)
		return -EINVAL;
	/* This bring-up driver never accepts a reset/trim-programming entry. */
	for (i = 0; i < regs->len; i += 4) {
		unsigned int reg = get_unaligned_le16(regs->data + i);

		if (reg < 3 || reg > 0x89 || (reg >= 0x76 && reg <= 0x7f))
			return -EINVAL;
	}
	amp->registers = regs->data;
	amp->register_bytes = regs->len;
	return 0;
}

static ssize_t runtime_status_show(struct device *dev,
				  struct device_attribute *attr, char *buf)
{
	struct aw88480 *amp = dev_get_drvdata(dev);
	unsigned int status = 0, volume = 0, vbat = 0, temp = 0;
	int ret = 0, len;

	mutex_lock(&amp->lock);
	if (amp->powered) {
		ret = regmap_read(amp->regmap, AW48_STATUS, &status);
		if (!ret)
			ret = regmap_read(amp->regmap, AW48_VOLUME, &volume);
		if (!ret)
			ret = regmap_read(amp->regmap, AW48_VBAT, &vbat);
		if (!ret)
			ret = regmap_read(amp->regmap, AW48_TEMP, &temp);
	}
	len = sysfs_emit(buf, "channel=%u powered=%u error=%d status=0x%04x read=%d gain=%u native=%u attenuation=%u volume=0x%04x vbat_raw=%u temp_raw=%u\n",
			 amp->channel, amp->powered, amp->last_error, status, ret,
			 amp->gain, amp->native_attenuation, amp->attenuation, volume,
			 vbat, temp);
	mutex_unlock(&amp->lock);
	return len;
}
static DEVICE_ATTR_RO(runtime_status);
static struct attribute *aw88480_attrs[] = {
	&dev_attr_runtime_status.attr, NULL
};
ATTRIBUTE_GROUPS(aw88480);

static void aw88480_cleanup(void *data)
{
	struct aw88480 *amp = data;

	cancel_delayed_work_sync(&amp->start_work);
	cancel_delayed_work_sync(&amp->monitor_work);
	mutex_lock(&amp->lock);
	amp->requested = false;
	aw88480_stop(amp);
	mutex_unlock(&amp->lock);
}

static void aw88480_assert_reset(void *data)
{
	gpiod_set_value_cansleep(data, 1);
}

static void aw88480_shutdown(struct i2c_client *i2c)
{
	aw88480_cleanup(i2c_get_clientdata(i2c));
}

static int aw88480_probe(struct i2c_client *i2c)
{
	struct device *dev = &i2c->dev;
	struct aw88480 *amp;
	int ret;

	amp = devm_kzalloc(dev, sizeof(*amp), GFP_KERNEL);
	if (!amp)
		return -ENOMEM;
	mutex_init(&amp->lock);
	INIT_DELAYED_WORK(&amp->start_work, aw88480_start_work);
	INIT_DELAYED_WORK(&amp->monitor_work, aw88480_monitor_work);
	i2c_set_clientdata(i2c, amp);
	amp->aw.dev = dev;
	amp->aw.i2c = i2c;
	amp->aw.chip_id = 0x2418;
	amp->aw.prof_info.prof_type = AW88395_DEV_NONE_TYPE_ID;
	amp->gain = AW48_GAIN_DEFAULT;
	ret = device_property_read_u32(dev, "awinic,audio-channel", &amp->channel);
	if (ret || amp->channel > 3)
		return -EINVAL;
	amp->aw.channel = amp->channel;
	amp->reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(amp->reset))
		return dev_err_probe(dev, PTR_ERR(amp->reset), "reset GPIO\n");
	ret = devm_add_action_or_reset(dev, aw88480_assert_reset, amp->reset);
	if (ret)
		return ret;
	amp->regmap = devm_regmap_init_i2c(i2c, &aw88480_regmap);
	if (IS_ERR(amp->regmap))
		return PTR_ERR(amp->regmap);
	amp->aw.regmap = amp->regmap;
	ret = aw88480_load_firmware(amp);
	if (ret)
		return dev_err_probe(dev, ret, "native ACF\n");
	gpiod_set_value_cansleep(amp->reset, 1);
	/* This action must run before devres releases the regmap and ACF memory. */
	ret = devm_add_action_or_reset(dev, aw88480_cleanup, amp);
	if (ret)
		return ret;
	dev_info(dev, "AW88480 channel=%u native register pairs=%u, reset; ID checked at PCM start\n",
		 amp->channel, amp->register_bytes / 4);
	return devm_snd_soc_register_component(dev, &aw88480_component, &aw88480_dai, 1);
}

static const struct of_device_id aw88480_of_match[] = {
	{ .compatible = "awinic,aw88480" },
	{ }
};
MODULE_DEVICE_TABLE(of, aw88480_of_match);
static struct i2c_driver aw88480_driver = {
	.driver = {
		.name = "aw88480",
		.of_match_table = aw88480_of_match,
		.dev_groups = aw88480_groups,
	},
	.probe = aw88480_probe,
	.shutdown = aw88480_shutdown,
};
module_i2c_driver(aw88480_driver);
MODULE_DESCRIPTION("Awinic AW88480 native-profile ASoC amplifier");
MODULE_LICENSE("GPL");
