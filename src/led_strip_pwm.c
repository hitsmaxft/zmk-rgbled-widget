#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/drivers/led_strip.h>
#include <zephyr/sys/printk.h>

#define LED_COUNT CONFIG_RGBLED_WIDGET_LED_COUNT

struct led_strip_pwm_data {
    const struct device *pwm_dev;
    uint32_t pwm_pin;
    uint8_t led_count;
};

/* PWM -> WS2812 bit-banging */
static void ws2812_send_pixel(const struct device *dev, uint8_t r, uint8_t g, uint8_t b)
{
    struct led_strip_pwm_data *data = dev->data;

    for (int color = 0; color < 3; color++) {
        uint8_t byte = (color == 0) ? g : ((color == 1) ? r : b);

        for (int bit = 7; bit >= 0; bit--) {
            uint32_t pulse = (byte & (1 << bit)) ? 800 : 400; // ns
            pwm_set(data->pwm_dev, data->pwm_pin, pulse + (1200 - pulse), pulse, 0);
        }
    }
}

/* LED Strip API 实现 */
static int led_strip_pwm_update_rgb(const struct device *dev, uint8_t *rgb, size_t len)
{
    struct led_strip_pwm_data *data = dev->data;

    if (len > data->led_count * 3) return -EINVAL;

    for (size_t i = 0; i < len / 3; i++) {
        ws2812_send_pixel(dev, rgb[i*3], rgb[i*3+1], rgb[i*3+2]);
    }
    return 0;
}

static const struct led_strip_driver_api led_strip_pwm_api = {
    .update_rgb = led_strip_pwm_update_rgb,
};

static struct led_strip_pwm_data ws2812_data = {
    .pwm_dev = DEVICE_DT_GET(DT_NODELABEL(pwm0)),
    .pwm_pin = 13,
    .led_count = LED_COUNT,
};

static int ws2812_init(const struct device *dev)
{
    ARG_UNUSED(dev);
    return 0;
}

DEVICE_DT_DEFINE(DT_NODELABEL(ws2812_pwm),
                 ws2812_init,
                 NULL,
                 &ws2812_data,
                 NULL,
                 POST_KERNEL,
                 CONFIG_LED_STRIP_INIT_PRIORITY,
                 &led_strip_pwm_api);