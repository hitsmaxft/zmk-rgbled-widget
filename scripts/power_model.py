#!/usr/bin/env python3
"""Overnight power model for cornix split halves with zmk-rgbled-widget.

Simulates the ext_power state machine of the widget plus baseline BLE/MCU
draw over a night of inactivity, for three firmware generations:

  1. pre-fix  : no IDLE listener; battery reports (every 60 s) re-enable the
                WS2812 rail for ~3 s each cycle.
  2. post-fix : PR #3 — IDLE (30 s) cuts ext_power immediately and battery
                reports no longer wake the LED path.
  3. post-fix : same, but assuming the widget was compiled out entirely
                (upper bound of what RGB optimization can ever save).

Outputs per-scenario average current, mAh per night, and % of a 700 mAh cell.
Also computes the unexplained residual versus the measured 4%/night.

Run: uv run python scripts/power_model.py
"""

NIGHT_S = 10 * 3600          # 10 h night
BATTERY_MAH = 700.0
STEP_S = 1.0

# ---- hardware current assumptions (mA) ------------------------------------
WS2812_QUIESCENT = 0.6       # per chip, rail on, all LEDs off (WS2812B typ.)
WS2812_LED_COUNT = 2
WS2812_GREEN_B64 = 4.5       # one LED green at brightness 64/255
EXT_POWER_IQ = 0.001         # load-switch quiescent, negligible

# ---- zmk / widget parameters (from .build/cornix_right/zephyr/.config) ----
IDLE_TIMEOUT_S = 30          # CONFIG_ZMK_IDLE_TIMEOUT=30000
BAT_REPORT_S = 60            # CONFIG_ZMK_BATTERY_REPORT_INTERVAL=60
BAT_LED_ON_S = 2.0           # CONFIG_RGBLED_WIDGET_BATTERY_BLINK_MS=2000
EXT_OFF_TIMEOUT_S = 1.0      # CONFIG_RGBLED_WIDGET_EXT_POWER_TIMEOUT_MS=1000
BOOT_LED_ON_S = 3.5          # boot battery(2s)+conn(1.5s) blinks then rail off

# ---- baseline (non-RGB) draw: the unknown we want to expose ---------------
# nRF52840 split CENTRAL without CONFIG_ZMK_SLEEP: radio must attend every
# 7.5 ms connection event (CONFIG_ZMK_SPLIT_BLE_PREF_INT=6) on 2 links.
# Literature/PPK2 reports for ZMK centrals in this mode: ~1..3 mA.
I_BASE_CENTRAL = 1.5         # conservative mid estimate
I_BASE_PERIPHERAL = 0.08     # peripheral uses slave latency -> low duty


def simulate_widget(fix: bool, central: bool) -> tuple[float, float]:
    """Return (avg_rail_mA, ext_on_fraction) for the RGB power rail."""
    t = 0.0
    rail_on_until = BOOT_LED_ON_S      # boot blinks keep the rail up briefly
    last_led_event = BOOT_LED_ON_S
    rail_on_s = 0.0
    led_on_s = 0.0

    while t < NIGHT_S:
        t += STEP_S
        # battery reporting wakes the LED path only pre-fix
        if not fix and (t % BAT_REPORT_S) < STEP_S:
            last_led_event = t
            rail_on_until = t + BAT_LED_ON_S + EXT_OFF_TIMEOUT_S
            led_on_s += BAT_LED_ON_S

        idle_cut = fix and t >= IDLE_TIMEOUT_S
        rail_on = (t < rail_on_until) and not idle_cut
        if rail_on:
            rail_on_s += STEP_S

    rail_ma_when_on = WS2812_LED_COUNT * WS2812_QUIESCENT + EXT_POWER_IQ
    # avg current in mA: (mA·s) / s * 1000 -> but we keep s in seconds:
    avg = (rail_on_s * rail_ma_when_on + led_on_s * WS2812_GREEN_B64) / NIGHT_S
    return avg, rail_on_s / NIGHT_S


def scenario(name: str, fix: bool, central: bool, base_ma: float) -> None:
    avg_rail, frac = simulate_widget(fix, central)
    total = avg_rail + base_ma
    mah = total * NIGHT_S / 3600
    pct = mah / BATTERY_MAH * 100
    print(f"{name:<42} rail={avg_rail:6.3f} mA (on {frac*100:5.2f}%) "
          f"base={base_ma:6.3f} mA  total={total:6.3f} mA  "
          f"{mah:6.1f} mAh/night  {pct:5.2f}% of {BATTERY_MAH:.0f} mAh")
    return total


def main() -> None:
    print(f"Night duration: {NIGHT_S/3600:.0f} h | battery: {BATTERY_MAH} mAh")
    print(f"Idle timeout {IDLE_TIMEOUT_S}s | battery report every {BAT_REPORT_S}s | "
          f"ext_power off after {EXT_OFF_TIMEOUT_S}s idle\n")

    pre_c  = scenario("pre-fix  (central  half)", fix=False, central=True,  base_ma=I_BASE_CENTRAL)
    post_c = scenario("post-fix (central  half)", fix=True,  central=True,  base_ma=I_BASE_CENTRAL)
    zero_c = scenario("no-widget(central  half) upper bound", fix=True, central=True, base_ma=I_BASE_CENTRAL)
    print()
    pre_p  = scenario("pre-fix  (peripheral half)", fix=False, central=False, base_ma=I_BASE_PERIPHERAL)
    post_p = scenario("post-fix (peripheral half)", fix=True,  central=False, base_ma=I_BASE_PERIPHERAL)

    print("\n--- attribution ---")
    saved = pre_c - post_c
    print(f"RGB fix saves on central:     {saved*NIGHT_S/3600:6.1f} mAh/night "
          f"({saved*NIGHT_S/3600/BATTERY_MAH*100:.2f}% of battery)")
    print(f"RGB total budget post-fix:    {post_c - I_BASE_CENTRAL:.3f} mA -> "
          f"fixing RGB further can save at most ~{(post_c-I_BASE_CENTRAL)*NIGHT_S/3600:.1f} mAh")

    # Deep sleep scenario (CONFIG_ZMK_SLEEP=y): after SLEEP_TIMEOUT the SoC
    # powers off entirely; the widget is already off from the IDLE point, so
    # only the BLE baseline during the 900 s idle window matters.
    SLEEP_TIMEOUT_S = 900
    I_POWEROFF = 0.002  # sys_poweroff RAM-retention only
    def deep_sleep_total(base_ma: float) -> float:
        # 30 s idle window draws base, then rail is already off (RGB fix),
        # sleep window: SoC is powered off -> ~RAM retention only
        active_s = min(SLEEP_TIMEOUT_S, NIGHT_S)
        return (base_ma * active_s + I_POWEROFF * (NIGHT_S - active_s)) / NIGHT_S
    ds_c = deep_sleep_total(I_BASE_CENTRAL)
    ds_p = deep_sleep_total(I_BASE_PERIPHERAL)
    print("\n--- deep sleep (CONFIG_ZMK_SLEEP=y) ---")
    for name, v in (("central ", ds_c), ("peripheral", ds_p)):
        print(f"post-fix+deepsleep ({name}):  {v:6.3f} mA  "
              f"{v*NIGHT_S/3600:6.1f} mAh/night  {v*NIGHT_S/3600/BATTERY_MAH*100:.2f}%")

    measured = 0.04 * BATTERY_MAH / (NIGHT_S / 3600)
    print(f"\nMeasured 4%/night implies:    {measured:.2f} mA average")
    print(f"Post-fix model predicts:      {post_c:.2f} mA (central) / {post_p:.2f} mA (peripheral)")
    resid = measured - post_c
    if resid > 0:
        print(f"Unexplained residual:         {resid:.2f} mA -- NOT attributable to RGB.")
        print("Likely sources: BLE baseline higher than estimate (central scanning,"
              "\n  connection-interval 7.5ms on 2 links), or the fixed firmware was not"
              "\n  flashed, or another always-on consumer (display, pull-ups, LDO iq).")


if __name__ == "__main__":
    main()
