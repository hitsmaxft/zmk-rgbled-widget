# WS2812 Code Path Improvements

## Summary

This document records the bug fixes and reliability improvements applied to the WS2812 LED strip code path in `zmk-rgbled-widget`.

---

## Fixes Applied

### 1. Kconfig syntax error (Kconfig:234)

**Problem**: `depends on CONFIG_RGBLED_WIDGET_WS2812` uses the `CONFIG_` prefix which is invalid in Kconfig syntax. This caused the entire "RGB LED Widget Connectivity Options" menu to be invisible in menuconfig — users could not configure BT channel colors through the menu system.

**Fix**: Changed to `depends on RGBLED_WIDGET_WS2812`.

---

### 2. `rgb_interpolate()` uint8_t underflow (widget.c)

**Problem**: The subtraction `(end->r - start->r)` operates on uint8_t values. When `end < start` (fade from bright to dark), the result wraps around to a large positive number (~250+), causing incorrect color output.

**Fix**: Cast to int16_t before subtraction, then CLAMP result to [0, 255].

---

### 3. Shared static `last_update` in animation engine (widget.c)

**Problem**: `update_led_animation()` used a single `static uint32_t last_update` shared across all LED indices. This dead code could cause confusion and bugs if future changes relied on it.

**Fix**: Removed the unused `last_update` variable entirely. The animation functions use `k_uptime_get_32()` modulo period directly, which is self-contained per invocation.

---

### 4. `can_share_led()` same-priority rejection (widget.c)

**Problem**: When the same status type (e.g. BLE connectivity) tries to update its LED color (e.g. switching BT profiles), the priority is equal. The old code had a special-case check for `PRIORITY_CRITICAL_BATTERY` that unconditionally blocked ALL updates including self-updates. Additionally the FIXME noted that same-priority non-shared LEDs could not be updated.

**Fix**: Simplified logic — equal or higher priority (lower numeric value) always succeeds. Lower priority can still acquire if the LED is marked shareable. This allows same-status-type updates and also permits critical battery to be cleared when battery recovers.

---

### 5. Mutating shared ZMK event data (widget.c)

**Problem**: `bat_ev->state_of_charge = display_level` modified the event struct in-place. Since ZMK events may be consumed by multiple listeners, other subscribers would receive the smoothed value instead of the actual hardware reading.

**Fix**: Removed the assignment. The EMA filter still gates whether `indicate_battery()` is called (early return when unchanged), but no longer tampers with the shared event.

---

### 6. Deep sleep does not disable ext_power (widget.c)

**Problem**: On `ZMK_ACTIVITY_SLEEP`, the code only sent black pixels via `set_rgb_leds(0, 0)` but left external power enabled. The delayed work timer may not fire reliably during deep sleep, leaving the WS2812 power rail drawing quiescent current indefinitely.

**Fix**: Added explicit `ext_power_disable()` in the sleep handler, with `k_work_cancel_delayable()` to prevent the timer from racing.

---

### 7. Debug TRAP logs left in production code (widget.c)

**Problem**: Three `LOG_WRN(">>> TRAP ...")` messages were left from debugging. They fire on every status change and message queue receive, polluting logs at WARNING level.

**Fix**: Converted to `LOG_DBG` with cleaned-up message text.

---

### 8. Thread stack size too small for sinf() (widget.c)

**Problem**: `led_process_thread` stack was 1024 bytes. The `ANIM_PULSE` path calls `sinf()` which can consume 300-500 bytes of stack on ARM soft-float platforms. Combined with message queue operations and nested function calls, this risks stack overflow.

**Fix**: Increased stack to 1536 bytes.

---

## Remaining Known Issues (Not Fixed)

| Issue | Notes |
|-------|-------|
| WAVE/RAINBOW animation types declared but not implemented | Fallback to STATIC; consider removing from enum if not planned |
| `widget.h` declares ~15 APIs with no implementation | Link errors if externally referenced; clean up or implement |
| Single 1580-line source file | Consider splitting into strip driver, animation engine, and indicator logic |
| `color_index_to_rgb` limited to 8 colors | Only 3-bit color space; expanding requires LUT or config changes |
| Empty `rgbled_ws2812.overlay` | Should contain example DT configuration for reference |
| CI does not build `rgbled_ws2812` shield | WS2812 path has no compile-time validation in CI |
