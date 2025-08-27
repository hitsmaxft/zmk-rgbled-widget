#include <zephyr.h>
#include <device.h>
#include <drivers/pwm.h>
#include <drivers/led_strip.h>

struct led_strip_pwm_data {
    const struct device *pwm_dev;
    uint32_t pwm_pin;
    uint8_t led_count;
};