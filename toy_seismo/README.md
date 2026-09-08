# toy_seismo — ESP32-8048S050C display firmware

Bring-up and firmware for the **Sunton / DIYmalls ESP32-8048S050C-I**: 5.0" 800×480
IPS, GT911 capacitive touch, ESP32-S3-WROOM-1 N16R8 (16 MB flash, 8 MB octal PSRAM).

First target is a **wall display for the live OAKM1 station**, reading `/v1/live` and
`/v1/events` from `seismo_server.py` on pi5. That needs no GPIO at all, so it is not
blocked by the pin budget below, and it exercises the display + touch stack that both
seismometer variants in `doc/toy-seismometer.md` need anyway.

## Build

```
pio run -d toy_seismo            # build
pio run -d toy_seismo -t upload  # flash
pio device monitor -p /dev/cu.usbserial-20132430 -b 115200
```

PlatformIO must run on **Python ≤ 3.13** — see "Toolchain notes".

## The pin budget

The RGB565 parallel panel eats 21 GPIOs before anything else. After the panel, touch
and backlight, the headers expose:

| header | pins | usable? |
|---|---|---|
| P1 | 43, 44 | **no** — UART0, and the CH340 is the only way to flash (19/20 are the S3's native USB pins, taken by touch) |
| P2 | 11, 12, 13 | yes — shared with the microSD SPI bus |
| P3 | 18, 19, 20 | 19/20 are the GT911 I²C bus; 18 is free (see below) |
| P4, P5 | 17, 18 (+3V3, GND) | yes |

So: **11, 12, 13, 17, 18.** Five pins.

- **GPIO18 is free by default.** The PlatformIO board definition lists it as the GT911
  interrupt, but the interrupt is *not connected* — it needs a 0 Ω resistor or solder
  bridge across **R17**. The board definition names the pin the INT would land on if
  you bridge it; that is not a wiring claim. (ESP3D's hardware docs are the source.)
- **GPIO33/34 are NOT free**, contrary to some listings — on an N16R8 part GPIO33–37
  belong to the octal PSRAM.

That is enough for an ADS1220 (MOSI 11, SCK 12, MISO 13, CS 17, DRDY 18) with the
microSD surviving on its own CS at GPIO10.

## Toolchain notes — three traps, all of which cost a session

**1. `CPLUS_INCLUDE_PATH` poisons every cross-compiler.**
`~/.zshrc` exports it at Apple's libc++ headers. GCC honours it for *all* targets, so
xtensa-esp32s3-gcc pulls macOS system headers and dies with `#error "No thread API"`.
`.zshrc`'s own `get_idf` alias unsets it; PlatformIO does not go through that alias, so
`scripts/clean_host_env.py` strips it as a pre-build step. **Do not delete that script.**

**2. The platform name `espressif32` is contested.**
pioarduino installs itself under the *same platform name* as the registry package, so a
bare `platform = espressif32` silently resolves to whichever is installed, not to the
registry. It must stay version-pinned (`espressif32@6.9.0` → Arduino 2.0.17 / IDF 4.4).

**3. The registry's `esp32_smartdisplay` "3.0.0" is a bad publish.**
It expects `GPIO_BCKL`, while every commit of the boards repo — including the one the
library's own submodule pins — defines `DISPLAY_BCKL`. It also uses `uint` and
`lv_display_t.sw_rotate`, neither of which exists in the versions it claims to support.
The working source is **2.1.1** (git `456360c`), vendored in `lib/` because PlatformIO's
git-client check fails on this machine.

### The version set — all four must move together

| piece | pin | why |
|---|---|---|
| platform | `espressif32@6.9.0` | Arduino 2.0.17 / IDF 4.4, which still has `esp_lcd_rgb_panel_config_t.{psram_trans_align, on_frame_trans_done, user_ctx}` and `flags.relax_on_idle`. IDF 5.x removed all four. |
| library | vendored 2.1.1 `456360c` | matches `DISPLAY_BCKL` |
| boards | `./boards` @ `05e8c10e` | the commit the library's submodule pins |
| LVGL | `9.2.2` exactly | `sw_rotate` is gone after this; an unpinned `^9.2.0` resolves to 9.5 and fails |

`boards/` is cloned, not vendored, and is gitignored:

```
git clone https://github.com/rzeldent/platformio-espressif32-sunton.git toy_seismo/boards
git -C toy_seismo/boards checkout 05e8c10e
```

## Factory firmware

The board ships running an LVGL **8** demo. `factory-demo-backup.bin` is a full 16 MB
dump taken before first flash (gitignored — it is 16 MB of vendor blob). Restore with:

```
esptool.py --chip esp32s3 --port <port> --baud 230400 write_flash 0 factory-demo-backup.bin
```

⚠️ The CH340 corrupts reads at 460800 (`Corrupt data, expected 0x1000 bytes`). Use
230400 or slower for bulk flash reads.

## Files

- `src/main.cpp` — bring-up diagnostic: colour bars (catches an R/B swap), touch
  coordinate readout (catches a mirrored axis), PSRAM/flash/resolution over serial.
- `scripts/clean_host_env.py` — pre-build environment scrubber, see trap 1.
- `include/lv_conf.h` — LVGL config, `LV_COLOR_DEPTH 16`, Montserrat 24/28/48 enabled.

## Display performance — the sync-loss investigation (2026-09-08)

**Symptom:** the panel "lost sync" — the image shifted sideways and stayed shifted.
That is Espressif's documented RGB-LCD failure: when DMA cannot feed the LCD
peripheral fast enough it emits dummy bytes, desynchronising the DMA read address
from the address the peripheral believes it is scanning, giving *"a permanently
shifted image"*.

**It was not a bandwidth ceiling. It was a bug in `src/main.cpp`.** Drawing into an
`lv_canvas` via the LVGL draw-layer API and calling `lv_canvas_finish_layer()`
invalidates the **whole canvas** regardless of how few pixels changed — 448 KB copied
PSRAM→PSRAM every frame, pushed through a 128 KB DMA buffer, against a scanout already
reading ~30 MB/s. Writing pixels straight into the RGB565 buffer and invalidating only
the touched column fixed it outright:

| | before | after |
|---|---|---|
| `trace_step` | 2963 µs | 130 µs |
| `lv_timer_handler` | 74528 µs | ~600 µs |
| loop rate | 11 fps | 174 fps |

**135×.** The tell was that mean ≈ worst and both were near-constant — a fixed cost, so
a full-screen repaint, not work proportional to what changed.

**This fixed most of it, but not all of it.** After the fix the panel is *far* better and
briefly looked perfect, but **mild glitching remains**, and it remains even with drawing
throttled to 30 columns/s — about 70x slower than this test ran, and ~4000x faster than
a real helicorder's 0.44 px/s. So the residual is not a workload problem, and no further
reduction in what we draw will remove it.

### Where that leaves the platform — measured, not assumed

Of Espressif's mitigations, IDF 4.4 gives us only two, and **both are now spent**:

| mitigation | available on IDF 4.4? | result |
|---|---|---|
| reduce PSRAM traffic | yes | done — 135x, most of the problem |
| lower the pixel clock | yes | **counter-productive**: below ~10-14 MHz the ST7262 free-runs |
| draw buffer in internal SRAM | yes | done — worst case 4610 -> 4150 us, marginal |
| `bounce_buffer_size_px` | **no** | IDF 5.x only |
| `CONFIG_LCD_RGB_RESTART_IN_VSYNC` | **no** | IDF 5.x only |
| `esp_lcd_rgb_panel_restart()` | **no** | IDF 5.x only |

Absence of the last three is verified in
`framework-arduinoespressif32/tools/sdk/esp32s3/include/esp_lcd/`, not inferred.

**The residual glitching is therefore a property of this stack, not of the hardware.**
The board's own factory firmware ran visibly clean, and Sunton build these against
ESP-IDF 5.x where bounce buffers exist. (We cannot diff against it: the factory image
was erased before flashing and the backup could not be taken — see below.)

**The open fork.** Removing the residual means IDF 5.x, and `esp32_smartdisplay` will
not compile there (that combination is what failed on 2026-09-08). That means a
different graphics layer — LovyanGFX supports this panel, the GT911, and bounce buffers.
It is a real piece of work and it is NOT yet justified: nothing establishes that mild
glitching matters for a wall display showing a slow helicorder. Decide it against the
actual application, not against this test.

⚠️ **Do not lower the pixel clock below the board default 16 MHz.** 8.2 MHz (for a 20 Hz
refresh) made the panel free-run and cycle colours — the ST7262 has a *minimum* pclk of
roughly 10–14 MHz. It also bought nothing: the full 135× came from the drawing fix, with
PCLK back at 16 MHz.

**Rule for this display: never invalidate more than changed.** A helicorder touches one
column per sample; anything that repaints the frame will desync the panel.

### Factory firmware backup — failed, and why

The 16 MB dump was attempted four times (460800, 230400, 115200 baud; two USB
positions) and failed every time with `Corrupt data, expected 0x1000 bytes but received
0xff6..0xffd bytes` — a few bytes short per 4 KB block, independent of baud rate. The
board sits behind a Thunderbolt dock's hub tree; macOS's built-in CH34x driver is the
likely culprit. **Reads corrupt; writes do not** — every `write_flash` passed its
on-device MD5 check at 460800. So flashing is reliable here and bulk reads are not.
