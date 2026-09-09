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

## The UI shell (`ui_shell.*`, `ui_icons.*`)

A reusable application shell, deliberately knowing nothing about seismometers:
fixed title bar (station / clock / Wi-Fi strength), a left rail of square icons, and a
content area. Up to 5 pages plus a "?" pinned at the bottom giving per-page help.
Geometry derives from `LV_HOR_RES`/`LV_VER_RES`, so it is not nailed to this panel.

**Pages are built once and shown/hidden, never rebuilt** — rebuilding a page's canvases
on every tap would be a ~610 KB burst and would desync the scanout instantly.

Icons are drawn as pixels (`ui_icons.cpp`), not loaded as images or symbol fonts: no
asset dependency, and recolouring for the active state is just a redraw. The **help "?"
is the exception** — it is a real glyph, because a question mark is a *character* and
looked like a stray arc when reconstructed from primitives.

## Display honesty — three decisions worth keeping

**1. The trace scale is logarithmic and FIXED, not auto-scaled.** Auto-scaling fills the
panel whatever is happening, so a passing truck and a felt earthquake look identical —
it tells the viewer that all ground motion is equally dramatic, which is a lie. ~39 px
per decade of µV, gridlines and a labelled y-axis at 1/10/100/1k either side of zero.
Range covered: 0.8 µV noise floor to the 6843 µV M3.3 of 2026-09-03.

**2. Amplitude colour bands**, five discrete steps: green < 10 µV (normal), lime to 30,
yellow to 100, orange to 300, red above. Because row position on a log trace *is*
amplitude, the bands are fixed horizontal stripes computed once; a column emits one rect
per band it crosses, usually two or three. Thresholds come from this station's measured
numbers, not from taste.
⚠️ There was briefly a sixth band splitting green at 3 µV. It made every quiet column
dark at the base and bright at the tip — it looked like new growth on a plant and implied
a distinction that does not exist. **A colour change should mark a change of meaning, not
a change of magnitude within the same meaning.**

**3. The spectrum axis is logarithmic in frequency, 0.5-50 Hz, with Hz labels.** Linear
gave the 1-15 Hz detection band the leftmost third while most of the width went to
20-50 Hz, which is nearly all house noise. Known lines are marked as labelled *regions*,
not seven ticks: 37.65/40/40.6/41 Hz span 3.35 Hz and cannot be resolved on a 700 px
full-range axis at any scaling, however well the FFT separates them.

## Trace density is what makes it look alive

The web dashboard draws ~1.5 px per sample and shows individual oscillations. At 5
samples/px (`COL_PERIOD_S = 0.05`) a min/max fill is the *honest* rendering but adjacent
columns merge into a featureless slab. `COL_PERIOD_S = 0.02` gives ~2 samples/px, where
the envelope IS the waveform. Density, not colour, is what made it dull.

## Weather page

Open-Meteo, fetched directly (no key), every 15 minutes, with a °C/°F toggle that also
flips km/h ↔ mph and re-renders from cache without refetching.
⚠️ `setInsecure()` is used deliberately — a public, unauthenticated endpoint that receives
nothing but a lat/lon. **Do not copy that pattern anywhere carrying credentials.**

No earthquake forecast appears, and the help page says why: nobody can predict a specific
earthquake days ahead. What is real is the background rate and post-event aftershock
probabilities.

## Debug scaffolding must not ship

Twice this bit us. A 48 KB benchmark array left in `.bss` starved WiFi's internal
allocations so the radio stopped associating — silently, with no allocation error. And a
raw sample counter (`+557`) sat in the user-facing status line for hours, meaning nothing
to a viewer. Check `paint_dropped()` / `paint_high_water()` in the serial log; keep
counters off the glass.

## Smooth scrolling: a playout buffer

Data arrives in bursts -- ~263 columns every ~5 s -- so draining "as fast as possible"
made the trace sprint across the screen and then sit still for four seconds. **Smoothness
does not come from draining faster.** It comes from draining at exactly the rate the data
was recorded, with a cushion deep enough to ride out the burstiness: the same idea as an
audio or video jitter buffer.

Each frame draws `dt / COL_PERIOD_S` columns -- the columns of real time that just elapsed
-- with a fractional credit accumulator, so 2.5 columns/frame comes out as an even
2,3,2,3 instead of truncating to 2 and falling behind. A slow servo nudges the rate +/-50%
to hold the queue near `COLQ_TARGET`, absorbing a feed that runs slightly fast or slow.
A hard cap at 4x nominal stops it ever sprinting again.

**The cost is latency, and it is shown on screen rather than hidden**: the status line
reads `delay`, and it is the total -- pi5's ~4 s feed age plus ~6 s of playout cushion.
That is the right trade for a wall display and the wrong one for anything you would react
to. `COLQ_TARGET` is the single knob; near zero it guarantees visible stalls, which is the
problem it was added to solve.

**Known remaining issue:** a slight stutter persists. Untested guesses, in the order worth
trying: the servo oscillating against the ~5 s burst period (lower `COLQ_SERVO`); the
20 fps frame quantisation against a 50 col/s target; or LVGL's own refresh timer beating
against the vsync wait.

## Weather: plain HTTP, and why TLS was the wrong answer

`api.open-meteo.com` answers on **plain http with no redirect**, so the weather fetch uses
it. That is not laziness -- it was the difference between working and not:

| | HTTPS | plain HTTP |
|---|---|---|
| internal heap free | 62,076 | **105,912** |
| largest free block | 18,420 | **63,476** |
| fetches | 1 OK at boot, then failed forever | 3/3 OK |

mbedTLS is built with `CONFIG_MBEDTLS_INTERNAL_MEM_ALLOC`, so it can only allocate from
INTERNAL SRAM and needs ~40 KB contiguous. Once the display's bounce buffers (2 x 48 KB)
are allocated, the largest free internal block is ~18-25 KB. The first handshake after
boot succeeded; every one afterwards failed, and the page kept showing its last good
fetch -- which is how it came to be displaying **yesterday's weather** while looking
perfectly current.

**Dropping TLS freed 44 KB of internal SRAM and tripled the largest block**, because
WiFiClientSecure holds buffers even between fetches. The alternative on the table was
halving the bounce buffers and degrading the display to pay for encryption on a public
forecast endpoint that receives nothing but a latitude and a longitude. Charles spotted
the http option; it is by far the better trade.

⚠️ This reasoning is specific to an unauthenticated public read. **Do not generalise it to
anything carrying credentials.**

## One shared scratch buffer (`scratch.*`)

`/v1/live` (~20 KB), `/v1/events` and the weather forecast each used to allocate their own
body buffer. They never overlap, so they share one 40 KB reservation in PSRAM, made once
at boot: no repeated allocation, no churn on the internal heap, and one place where the
size is decided instead of three separate guesses.

## Never present stale data as current

The TLS failure hid for a day because a failed refresh silently left the previous fetch on
screen. The weather stamp now flips to **"STALE - refresh failing"** in red if the last
success is over 40 minutes old. Any panel that caches a remote value needs this; the
failure mode of quietly showing old numbers is worse than showing none.

## The limit: an RGB panel and a WiFi radio conflict on this SoC

Measured, not assumed, and the most useful result of the whole exercise.

**The symptom:** constant horizontal stripe noise in the top ~100 rows whenever the
network is busy. **The A/B that pinned it:** a network task that exists, is pinned to
core 0, and fetches *nothing* -> display perfectly clean. The same task fetching -> stripes.

**The measurement that identified the mechanism:** throttling reads to 1 KB every 8 ms
(~125 KB/s, spreading a 19 KB body over ~150 ms instead of a single burst) changed
**nothing**. If this were PSRAM bandwidth, that would have fixed it. It is not bandwidth.

**It is interrupt latency.** `CONFIG_LCD_RGB_ISR_IRAM_SAFE` is unset in the precompiled
Arduino libraries, so the bounce-buffer refill ISR executes from flash -- and so do the
WiFi driver and lwIP. Concurrent flash instruction fetch delays the refill past the point
where the LCD FIFO runs dry, however few bytes are actually moving.

**Ruled out along the way**, each by measurement rather than argument:
- WiFi buffers in PSRAM (`CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP` is unset -- they are internal)
- the scratch buffer's placement (glitches identically in PSRAM or internal SRAM)
- the spectrum page's ~430 KB/5 s of repaint (removed entirely; no change)
- raw bandwidth (see the throttle result above)

**Bounce depth was enough.** At **50 lines** (2 x 80 KB of internal SRAM, ~5.2 ms of
buffered scanout) the display is **clean with networking running**. Depth is how you
survive a late ISR, and ~5.2 ms of slack covers the delay WiFi imposes. Building ESP-IDF
from source with the refill ISR in IRAM remains the principled fix, but it is not needed.

⚠️ **What is NOT established:** the final step changed bounce depth 30 -> 50 *and* moved
the scratch buffer back to PSRAM in one flash, so their individual contributions are
untested. The paced drawing, 20 fps timing and throttled reads were all already in place
and may each be load-bearing. What is measured is that **this combination is clean**; do
not assume any single element can be removed.

The working configuration:
- `BOUNCE_LINES 50` (2 x 80 KB internal SRAM)
- 20 fps via `VSYNC_FRONT_PORCH=484`, PCLK unchanged at 16 MHz
- all drawing paced through the paint queue and drained in vertical blanking
- network on its own core, reads throttled to 1 KB / 8 ms

**For the standalone instrument** this is all headroom: an IMU read over SPI with the
radio down removes the contending flash workload entirely, which was the only thing the
bounce depth had to absorb.

## Acceptance criterion for display artefacts

Charles, 2026-09-09: **a glitch once every ten minutes is acceptable; once a second is
not.** Worth stating because it changes what "done" means -- chasing zero is where the
expense lives, and a rare artefact on a wall display costs nothing.

Practical consequences:
- an NTP sync once an hour, or a weather fetch every 15 minutes, are comfortably inside
  tolerance even if each causes one momentary artefact;
- the continuous 19 KB/4 s seismic feed was the only traffic frequent enough to matter,
  and it is the one that had to be made clean;
- do not spend internal SRAM, latency or complexity buying perfection past this line.

## The clock is independent of pi5

UTC comes from **SNTP** (`pool.ntp.org`, `time.cloudflare.com`), with the seismic feed's
`t_end + age` as fallback. The info page reports which is in charge -- `clock NTP` or
`clock pi5 feed` -- so a silent fallback cannot hide.

The feed-derived clock was fine while pi5 was the only source, but it stopped whenever
pi5 did, and the standalone IMU instrument has no feed at all. SNTP costs a few hundred
bytes an hour against the 19 KB every 4 s the display already survives.

## The intermittent glitch: what has been eliminated

Still unsolved at the end of 2026-09-09, but the elimination list is solid and every entry
was killed by measurement rather than argument. Recorded so nobody repeats the work.

**Symptom:** horizontal stripe noise in the top ~100 rows. Comes in EPISODES lasting
minutes, with clean stretches between. Only ever with network traffic running.

| Ruled out | By what |
|---|---|
| drawing / paint load | glitching observed at `colq_depth 191` -- *below* the 300 target, i.e. drawing slower than nominal; `paint dropped = 0` throughout |
| desync-and-restart | 0 late frames in 3,600 consecutive (frame timing is exact: 1200/min at 20 fps, worst == nominal) |
| raw bandwidth | throttling reads to 1 KB/8 ms (~125 KB/s, a 19 KB body spread over ~150 ms) changed **nothing** |
| memory fragmentation / leaks | it *recovers*, and memory does not spontaneously defragment (Charles); corroborated by `largest_free_block` staying **constant** at 18,420 rather than shrinking |
| spectrum rendering | page removed entirely (~430 KB/5 s of repaint gone); no change |
| scratch buffer placement | identical behaviour in PSRAM and in internal SRAM |
| WiFi buffers in PSRAM | `CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP` unset -- they are internal |

**What survives:** flash-contention from radio *activity*. The bounce-buffer refill ISR
runs from flash (`CONFIG_LCD_RGB_ISR_IRAM_SAFE` unset) and so do the WiFi driver and lwIP.
The cost is not bytes but retransmissions and driver work, which vary with channel
conditions on exactly the minutes-long timescale observed -- and an idle network task is
perfectly clean at any memory placement.

**How it is being tested:** the minute report now logs RSSI and per-fetch DURATION.
Duration is the proxy for channel quality -- the same bytes taking 2 s instead of 200 ms
means retransmission. If episodes coincide with slow fetches, that is the mechanism. If
fetch timings stay flat through an episode, the radio is exonerated too and everything
under our control has been eliminated.

## Two instrument lessons

**The measurement was destroying the state.** Opening the serial port asserts DTR/RTS and
reboots the ESP32, so every check erased the episode being measured and reset uptime to
zero -- "the software version of Heisenberg uncertainty". Clearing DTR/RTS *after* open()
does not help; the pulse has already happened, and on this CH340 setting them before open
does not help either. The fix is `tools/monitor.py` run **once** as a long-lived logger
writing to a file, with the file read instead of the port. Flashing still requires
stopping it first -- upload and monitor cannot share the port.

**Match the instrument to the observer.** Marking episode start/stop needs continuous
attention. Once Charles was glancing over occasionally, that instrument could only produce
bad data, so a tap became a POINT observation -- "glitching right now" -- which is all a
glance can honestly report. Positives are evidence; absence of a tap is not evidence of
clean.
