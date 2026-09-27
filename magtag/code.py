# code.py -- Adafruit MagTag as a portable helicorder (CircuitPython 10.x).
#
# The device is deliberately dumb: fetch a finished 296x128 4-grey BMP from the
# dashboard (/magtag/<page>.bmp, rendered by dashboard/magtag.py), blit it, refresh.
# All layout lives on the server, so changing a page is a deploy, not a re-flash.
#
# Buttons A..D pick pages: helicorder, stats, weather, last quake (see magtag_pages.py).
# Pressing the button for the page already showing toggles the four NeoPixels white
# instead: a light for reading the panel in the dark. It switches itself off after
# SEISMO_LIGHT_S seconds (default 10), or on the next press of that button.
#
# DEEP SLEEP between refreshes, for battery life (~6 days on 420 mAh at 5 min, est.):
#   - a TIMER wake refreshes the current page and goes straight back to sleep;
#   - a BUTTON wake (A..D are pin alarms) acts on that press, then stays awake
#     AWAKE_S so a run of presses doesn't pay a wake each, then sleeps;
#   - the page survives sleep in alarm.sleep_memory[0].
# Sleep restarts the VM, so the in-memory bitmap comes back BLANK (all black) while
# the panel still shows the last image. A failed fetch therefore does NOT refresh:
# the old image stays (its clock says how stale), a button press that failed flashes
# one pixel red, and the error goes to the serial console.
# On USB, CircuitPython fakes deep sleep (USB stays up), so behaviour is testable
# there but the current draw is not.
#
# Libraries (from the CircuitPython bundle, into CIRCUITPY/lib):
#   adafruit_requests, adafruit_connection_manager, neopixel
# Settings (CIRCUITPY/settings.toml, see settings.toml.example):
#   CIRCUITPY_WIFI_SSID, CIRCUITPY_WIFI_PASSWORD, SEISMO_URL, SEISMO_REFRESH_S,
#   SEISMO_LIGHT (0..1 brightness, default 1.0), SEISMO_LIGHT_S (auto-off, default 10)
import os
import time

import adafruit_connection_manager
import alarm
import adafruit_requests
import bitmaptools
import board
import digitalio
import displayio
import keypad
import neopixel
import wifi

URL = os.getenv("SEISMO_URL", "https://seismo.mcguinness.ai")
REFRESH_S = int(os.getenv("SEISMO_REFRESH_S", "300"))   # e-ink: >= 180 s is kind to the panel
PAGES = ("heli", "stats", "weather", "event")   # buttons A..D
W, H = 296, 128
LIGHT = float(os.getenv("SEISMO_LIGHT", "1.0"))
LIGHT_S = float(os.getenv("SEISMO_LIGHT_S", "10"))
AWAKE_S = 10                            # after a button wake, stay up this long
BUTTONS = (board.BUTTON_A, board.BUTTON_B, board.BUTTON_C, board.BUTTON_D)

display = board.DISPLAY
bitmap = displayio.Bitmap(W, H, 4)
palette = displayio.Palette(4)          # index == grey level, same order as the server
palette[0], palette[1], palette[2], palette[3] = 0x000000, 0x555555, 0xAAAAAA, 0xFFFFFF
group = displayio.Group()
group.append(displayio.TileGrid(bitmap, pixel_shader=palette))
display.root_group = group

# The NeoPixel rail is switched by an ACTIVE-LOW pin: low powers the pixels. Keep it
# high (rail off) whenever the light is off, so the pixels draw nothing at all.
_np_power = digitalio.DigitalInOut(board.NEOPIXEL_POWER)
_np_power.switch_to_output(value=True)
pixels = neopixel.NeoPixel(board.NEOPIXEL, 4, brightness=LIGHT, auto_write=False)
light_on = False
light_since = 0.0


def toggle_light():
    global light_on, light_since
    light_on = not light_on
    light_since = time.monotonic()
    if light_on:
        _np_power.value = False
        time.sleep(0.01)                  # let the rail come up before the data
        pixels.fill((255, 255, 255))
        pixels.show()
    else:
        pixels.fill(0)
        pixels.show()
        _np_power.value = True


def flash_red():
    """One pixel, one second: the press was heard but the fetch failed."""
    _np_power.value = False
    time.sleep(0.01)
    pixels.fill(0)
    pixels[0] = (255, 0, 0)
    pixels.show()
    time.sleep(1)
    pixels.fill(0)
    pixels.show()
    _np_power.value = True


_session = None


def session():
    global _session
    if not wifi.radio.connected:
        wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"),
                           os.getenv("CIRCUITPY_WIFI_PASSWORD"))
    if _session is None:
        pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
        ssl = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
        _session = adafruit_requests.Session(pool, ssl)
    return _session


def fetch(page):
    """Download the page BMP and blit it. The server sends a TOP-DOWN 8-bit BMP whose
    palette indices are the grey levels and whose rows carry no padding, so the pixel
    block after the header offset IS the bitmap, byte for byte."""
    # Cloudflare fronts the public site and turns away anonymous clients.
    r = session().get(f"{URL}/magtag/{page}.bmp",
                      headers={"User-Agent": "OAKM1-MagTag/1"}, timeout=30)
    try:
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        data = r.content
    finally:
        r.close()
    off = int.from_bytes(data[10:14], "little")
    if data[:2] != b"BM" or len(data) - off != W * H:
        raise RuntimeError(f"bad image ({len(data)} bytes)")
    bitmaptools.arrayblit(bitmap, memoryview(data)[off:])


def show(page, pressed=False):
    t0 = time.monotonic()
    try:
        fetch(page)
    except Exception as e:      # see the header: never refresh a blank bitmap
        _drop_session()
        print(f"{page}: fetch FAILED after {time.monotonic() - t0:.1f}s: "
              f"{type(e).__name__}: {e}")
        if pressed:
            flash_red()
        return
    t1 = time.monotonic()
    wait = display.time_to_refresh
    time.sleep(wait)
    display.refresh()
    # One line per page shown, on the serial console: where the time went.
    print(f"{page}: fetch {t1 - t0:.1f}s, panel wait {wait:.1f}s, "
          f"refresh {time.monotonic() - t1 - wait:.1f}s")


def _drop_session():
    global _session
    _session = None


def press(k):
    """A button: switch page, or toggle the light if it's this page's own button."""
    global page
    if PAGES[k] == page:
        toggle_light()
    else:
        page = PAGES[k]
        show(page, pressed=True)


idx = alarm.sleep_memory[0]
page = PAGES[idx] if idx < len(PAGES) else PAGES[0]   # power-on: memory is arbitrary
wake = alarm.wake_alarm

if isinstance(wake, alarm.time.TimeAlarm):
    show(page)                                        # scheduled: refresh, sleep again
else:
    # Button wake, or a cold boot / reset: act, then stay up for follow-up presses.
    if isinstance(wake, alarm.pin.PinAlarm):
        press(BUTTONS.index(wake.pin))
    else:
        show(page)
    keys = keypad.Keys(BUTTONS, value_when_pressed=False, pull=True)
    time.sleep(0.05)
    keys.events.clear()           # the wake press may still be held: don't count it twice
    last_act = time.monotonic()
    while True:
        ev = keys.events.get()
        now = time.monotonic()
        if ev and ev.pressed:
            press(ev.key_number)
            last_act = time.monotonic()
        elif light_on and now - light_since >= LIGHT_S:
            toggle_light()                            # auto-off
        elif not light_on and now - last_act >= AWAKE_S:
            break
        time.sleep(0.05)
    keys.deinit()                 # the pins are needed as alarms now

alarm.sleep_memory[0] = PAGES.index(page)
if light_on:
    toggle_light()
while display.busy:               # never cut power mid-refresh
    time.sleep(0.1)
print(f"sleeping {REFRESH_S}s on {page}")
alarm.exit_and_deep_sleep_until_alarms(
    alarm.time.TimeAlarm(monotonic_time=time.monotonic() + REFRESH_S),
    *[alarm.pin.PinAlarm(pin=b, value=False, pull=True) for b in BUTTONS])
