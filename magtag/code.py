# code.py -- Adafruit MagTag as a portable helicorder (CircuitPython 9.x).
#
# The device is deliberately dumb: fetch a finished 296x128 4-grey BMP from the
# dashboard (/magtag/<page>.bmp, rendered by dashboard/magtag.py), blit it, refresh.
# All layout lives on the server, so changing a page is a deploy, not a re-flash.
#
# Buttons A..D pick pages. Only the helicorder exists yet; the others just refresh.
#
# Libraries (from the CircuitPython bundle, into CIRCUITPY/lib):
#   adafruit_requests, adafruit_connection_manager, adafruit_display_text
# Settings (CIRCUITPY/settings.toml, see settings.toml.example):
#   CIRCUITPY_WIFI_SSID, CIRCUITPY_WIFI_PASSWORD, SEISMO_URL, SEISMO_REFRESH_S
import os
import time

import adafruit_connection_manager
import adafruit_requests
import bitmaptools
import board
import displayio
import keypad
import terminalio
import wifi
from adafruit_display_text import label

URL = os.getenv("SEISMO_URL", "https://seismo.mcguinness.ai")
REFRESH_S = int(os.getenv("SEISMO_REFRESH_S", "300"))   # e-ink: >= 180 s is kind to the panel
PAGES = ("heli",)                                       # button index -> page; more to come
W, H = 296, 128

display = board.DISPLAY
bitmap = displayio.Bitmap(W, H, 4)
palette = displayio.Palette(4)          # index == grey level, same order as the server
palette[0], palette[1], palette[2], palette[3] = 0x000000, 0x555555, 0xAAAAAA, 0xFFFFFF
group = displayio.Group()
group.append(displayio.TileGrid(bitmap, pixel_shader=palette))
status = label.Label(terminalio.FONT, text="", color=0x000000, background_color=0xFFFFFF,
                     x=4, y=H - 8)
group.append(status)
display.root_group = group

keys = keypad.Keys((board.BUTTON_A, board.BUTTON_B, board.BUTTON_C, board.BUTTON_D),
                   value_when_pressed=False, pull=True)

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


def show(page):
    try:
        fetch(page)
        status.text = ""
    except Exception as e:      # keep the last good image; say why it's stale
        status.text = f"{type(e).__name__}: {e}"[:48]
        _drop_session()
    time.sleep(display.time_to_refresh)
    display.refresh()


def _drop_session():
    global _session
    _session = None


page = PAGES[0]
show(page)
last = time.monotonic()
while True:
    ev = keys.events.get()
    if ev and ev.pressed:
        if ev.key_number < len(PAGES):
            page = PAGES[ev.key_number]
        show(page)
        last = time.monotonic()
    elif time.monotonic() - last >= REFRESH_S:
        show(page)
        last = time.monotonic()
    time.sleep(0.05)
