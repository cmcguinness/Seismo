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

**That fixed most of it. A second change fixed the rest** — see "Cutting scanout
bandwidth" below. Throttling the drawing rate did *not* help, which was the clue: the
residual survived at 30 columns/s, ~4000x faster than a helicorder's 0.44 px/s, so it was
never about how much we drew. It was about what the *panel* was drawing.

### Cutting scanout bandwidth — frame rate and pixel clock are separable

**This is the fix for the residual glitching, and it is the non-obvious one.**

The RGB peripheral fetches framebuffer bytes *only during active pixels* — during
blanking it fetches nothing. So the continuous PSRAM read rate is set by the **frame
rate**, while the panel's timing controller locks to the **pixel clock**. Those are
independent, and lengthening the vertical blanking separates them:

```
before:  16 MHz / (820 x 500) = 39 fps  ->  800*480*39*2 = 29.9 MB/s
after:   16 MHz / (820 x 976) = 20 fps  ->  800*480*20*2 = 15.4 MB/s
```

One flag: `ST7262_PANEL_CONFIG_TIMINGS_VSYNC_FRONT_PORCH` 8 -> 484. **Halves the traffic
the display forces onto the PSRAM bus, at 16 MHz PCLK, with the panel still locked.**

⚠️ Do NOT get here by lowering PCLK instead. 8.2 MHz for the same 20 Hz made the panel
free-run and cycle colour — the ST7262 has a minimum pixel clock around 10-14 MHz.
Espressif's docs say "reduce the pixel clock"; on this panel the correct move is to
reduce the *frame rate* and leave the pixel clock alone.

### Where that leaves the platform

Of Espressif's listed mitigations, IDF 4.4 gives us two — but the list is not exhaustive,
and the blanking trick above is not on it:

| mitigation | available on IDF 4.4? | result |
|---|---|---|
| reduce PSRAM traffic | yes | done — 135x, most of the problem |
| **longer vertical blanking** | yes | **done — 29.9 -> 15.4 MB/s scanout; this fixed the residual** |
| lower the pixel clock | yes | **counter-productive**: below ~10-14 MHz the ST7262 free-runs |
| draw buffer in internal SRAM | yes | done — worst case 4610 -> 4150 us, marginal |
| throttle the drawing rate | yes | no effect — the residual was never workload |
| `bounce_buffer_size_px` | **no** | IDF 5.x only |
| `CONFIG_LCD_RGB_RESTART_IN_VSYNC` | **no** | IDF 5.x only |
| `esp_lcd_rgb_panel_restart()` | **no** | IDF 5.x only |

Absence of the last three is verified in
`framework-arduinoespressif32/tools/sdk/esp32s3/include/esp_lcd/`, not inferred.

**The display is now stable on this stack, and no platform migration is needed.** That
conclusion replaces an earlier one in this file's git history which said the residual was
structural and that removing it required IDF 5.x and a different graphics layer. That was
wrong — written after declaring the available mitigations "spent" when one had simply not
been thought of. Recorded here because the wrong version was committed first.

If a much heavier UI ever does hit the wall, the untried levers in rough order are:
draw the trace straight into the framebuffer with `esp_lcd_panel_draw_bitmap()` (skipping
the canvas, draw buffer and LVGL invalidation entirely — ~560 bytes per column), then
IDF 5.x for bounce buffers, which would mean replacing `esp32_smartdisplay` with
LovyanGFX.

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

## Live helicorder (`src/main.cpp`)

Polls `/v1/live` on pi5 and scrolls the ground motion. Credentials live in
`include/wifi_secrets.h`, which is **gitignored** — this repo is public. Copy
`wifi_secrets.h.example` and fill in SSID/password.

- **One pixel column = `COL_PERIOD_S` seconds**, drawn as a **min/max envelope**, not a
  decimation: 100 samples share a column at 1 s/col and picking one would alias away
  exactly the spikes worth seeing. This single constant decides whether the display reads
  as live (0.05 → 20 px/s, 40 s across) or as a chart recorder (1.0 → 1 px/s, 13.3 min
  across, which looks *frozen*).
- **Columns are binned by absolute sample time** from `t_end`, so a Wi-Fi dropout leaves a
  correct blank gap rather than silently compressing time.
- **Auto-scale tracks a slow envelope average, not the peak** (`doc/toy-seismometer.md`'s
  `ENV_FRAC` trick), so a quiet night still shows life and one door slam does not flatten
  the next ten minutes. Columns that would clip render **red** rather than truncating
  silently.
- **Adaptive polling.** pi5 refreshes the window in ~5.5 s blocks; a fixed 2 s poll spent
  half its fetches pulling 20 KB to learn nothing had changed.

### Four bugs worth not repeating

1. **`http.setReuse(false)` is mandatory.** `seismo_server.py` is a
   `BaseHTTPRequestHandler` — HTTP/1.0, closes after every response — while HTTPClient
   defaults to keep-alive and reuses the dead socket, giving an endless `-1 connection
   refused` cascade.
2. **Don't hand-roll the body reader.** The first version stream-parsed the array off the
   socket "to keep memory O(1)". 20 KB against ~130 KB of free internal heap was never
   the constraint, and the optimisation cost three bugs — a byte-matcher that assumed
   `"uv":[` when Python's `json.dumps` writes `"uv": [` **with a space**; a non-blocking
   tail read that missed `t_end` because it arrives *after* the array; and abandoned
   half-read sockets that pinned server threads against seismo_server's listen backlog
   of **5**, wedging it for every client. `http.getString()` then parse.
3. **Use pi5's IP, not its hostname.** The ESP32 resolves via the router's DNS, which does
   not necessarily know a bare LAN name that the Mac resolves fine.
4. **The board is 2.4 GHz only** and lands on `192.168.4.x/22` — same subnet as pi5's
   `192.168.5.30`, but check `mask` before assuming a routing problem.

⚠️ **The radio must never come up near the geophone.** See `BACKLOG.md` — an ESP32's
transmitter recreates the Wi-Fi dongle noise that corrupted ADS1256 reads. This panel is
a house display; that rule binds if it ever moves to the garage.

## The IDF 5.x port (env `s050-idf5`) — what finally made the display stable

The IDF 4.4 build degraded as the display got richer and ended in a **dead scanout**:
firmware still fetching and advancing its cursor in the logs while the panel showed a
stale frame. IDF 4.4 has no recovery API, so only a reboot cleared it.

**No LovyanGFX was needed.** On IDF 5.x, `esp_lcd` exposes what we came for directly, so
the port is ~150 lines of display init (`src/display_esp_lcd.cpp`) and the entire
application — helicorder, spectrum, events, Wi-Fi — was untouched. Both environments
coexist; `display_backend.h` picks one.

### The four things that had to be true together

Each was necessary; none alone was sufficient, which is why this took so long.

1. **Bounce buffers** (`bounce_buffer_size_px`, IDF 5.x only). The LCD scans out of two
   internal-SRAM buffers refilled by interrupt from the PSRAM framebuffer. **30 lines**,
   not Espressif's suggested 10 — 10 left visible horizontal stripe noise in the top
   ~100 rows. Must divide the frame evenly: 800x480 = 384000 px, 800x30 = 24000,
   384000/24000 = 16 exactly. Paid for by shrinking the LVGL draw buffer 40 -> 20 lines;
   internal SRAM does more good feeding the scanout than making render strips bigger.
2. **The 20 fps timing, kept.** Bounce buffers are NOT a licence to return to the board's
   default 39 fps. That scanout rate was measured glitchy on this panel; running it here
   just spends the bounce buffers' margin on nothing. `VSYNC_FRONT_PORCH=484`, PCLK
   untouched at 16 MHz.
3. **Paced drawing, still.** Nothing about IDF 5 removes the rule that a large single
   invalidate desyncs the scanout. The column queue and the spectrum strips stay.
4. **NO periodic `esp_lcd_rgb_panel_restart()`.** Restarting DMA disrupts a frame, so
   calling it on a timer injects a glitch every interval *by design* — it made things
   visibly worse. `CONFIG_LCD_RGB_RESTART_IN_VSYNC` is already `1` in this framework and
   restarts automatically, only when the hardware has actually desynced. The manual call
   stays available as a lever, unused.

### `CONFIG_LCD_RGB_ISR_IRAM_SAFE` is NOT set

Verified absent from the precompiled Arduino libs' sdkconfig. The bounce-buffer refill
ISR therefore stalls whenever the flash cache is disabled. Larger bounce buffers buy
tolerance for that, not immunity. Flipping it means building ESP-IDF from source instead
of using the Arduino framework — a much bigger change, not currently justified.

## ⚠️ LVGL's printf has NO float support

`lv_label_set_text_fmt(lbl, "%.1f uV", x)` emits a literal **`f`** and shifts every later
argument, so `"rms %.1f uV  age %.1fs  +%u"` rendered as `rms 1 uV age fs +1/1/98692`.
Every number on the display was wrong while the serial logs were perfectly correct —
the values were right in the program and wrong only on the glass.

**Use `snprintf` into a buffer, then `lv_label_set_text()`.** newlib's snprintf does not
depend on LVGL's build configuration. Found only from a photograph; no amount of log
reading would have shown it.

## The paint queue (`src/paint.h` / `paint.cpp`)

Charles's design, and it is the right shape: **application code enqueues drawing
primitives whenever it likes and never blocks; a drainer executes them inside the
vertical blanking interval, as fast as possible but no faster.** Work that does not fit
in one frame lands in the next. Nothing bursts, nothing is lost, and no drawing site has
to know anything about bandwidth.

That inversion matters because the constraint is genuinely awkward to distribute: the
panel scans an 800x480x2 framebuffer out of PSRAM continuously, the bus measures ~40 MB/s
total, and a single operation holding it beyond ~1 ms starves the LCD FIFO and desyncs
the scanout permanently. Before the queue, *every* drawing site had to be individually
careful, and every new panel re-broke the display.

- `paint_rect()` / `paint_vline()` — enqueue, non-blocking. Overflow drops the **oldest**
  command: on a scrolling display the freshest pixels are the ones worth keeping, and
  dropping newest would freeze the trace.
- `paint_drain(budget_px)` — called once per frame from inside the blanking window.
  800 x 60 px = 96 KB, about 3.4 ms of flush at the measured 28.6 MB/s, comfortably
  inside the ~25 ms of blanking.
- One coalesced invalidate per target per drain; LVGL then renders that bbox in
  10-line strips, each sized to the latency budget.

Text and widgets stay with LVGL — they redraw rarely and were never the problem. The
queue owns the high-rate pixel traffic: helicorder and spectrum.

## ⚠️ lv_obj_invalidate_area() takes ABSOLUTE screen coordinates

Not canvas-local ones. This cost an hour and hid as two different bugs:

- the **spectrum canvas at y=284** had local rows 0..103 mapped to absolute rows 0..103,
  which do not intersect it at all -> it never repainted and rendered permanently blank,
  while every pixel was being computed and written correctly;
- the **trace canvas at y=52** partially overlapped, so it appeared to work while its
  bottom quarter was almost certainly never refreshing.

The partial failure hid the total one. Offset by `lv_obj_get_coords()` before invalidating.

## Measured memory bandwidth (this board, panel running)

```
PSRAM  read :   25.3 MB/s      SRAM   read :   47.8 MB/s
PSRAM  write:   35.5 MB/s      SRAM->PSRAM :   28.6 MB/s   (the LVGL flush path)
scanout     :   15.4 MB/s continuous at 20 fps  (29.9 at the board default 39 fps)
internal heap: ~86 KB free, ~32 KB largest block
```

**The SoC is under-provisioned for this panel.** At the native 39 fps the scanout alone
wants 29.9 of ~40 MB/s -- 75% of memory bandwidth just to keep the screen lit. Dropping
to 20 fps leaves ~25 MB/s for the application, a 2.5x increase in headroom.

But the binding constraint is **latency, not throughput**: at 20 fps the panel needs a
line every ~104 us, while a full framebuffer write is 768 KB / 28.6 MB/s = **27 ms**.
A single full-frame repaint blocks the bus ~250x longer than the panel tolerates. That
is why *pacing* fixed what *reducing* could not.

**PSRAM is 7 MB and irrelevant; internal SRAM is ~86 KB and decides everything.** Bounce
buffers, the LVGL draw buffer, the paint queue and WiFi's own buffers all compete for it.
A leftover 48 KB benchmark array in `.bss` was enough to stop the radio associating --
silently, with no allocation error anywhere.

## Live UTC clock without an RTC

The board has no RTC, but `/v1/live`'s `t_end` **is** Unix epoch, so pi5's clock arrives
on every fetch; `millis()` carries it between. Good to a few hundred ms of poll latency:
fine for reading a detection list, not for picking arrivals.
