// Live helicorder for the Sunton ESP32-8048S050C-I, fed by seismo_server.py
// (/v1/live) on the LAN. See README.md for the pin budget, the pinned version
// set, and the display-bandwidth rules that this file has to respect.
//
// TWO RULES THIS FILE EXISTS TO OBEY (both learned the hard way, 2026-09-08):
//
//   1. Never invalidate more than changed. The panel scans its framebuffer out
//      of PSRAM continuously; any repaint competes with that, and a full-frame
//      repaint desyncs the scanout into a permanently shifted image. We touch
//      ONE column per second and invalidate exactly that column.
//   2. Never build a JSON document from /v1/live. The payload is 3000 floats,
//      ~25 KB; a DOM would cost more RAM than the trace. We stream-parse it
//      straight off the socket, so memory is O(1) in the sample count.

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "display_backend.h"
#include "wifi_secrets.h"
#include "spectrum.h"
#include "paint.h"

// ---------------------------------------------------------------- geometry --
// 800x480 split into four bands. Sizes are deliberate: the trace gets the most
// room because it is the instrument; the spectrum gets enough height to read a
// 30 dB range; the event strip gets three rows.
#define TRACE_X       0
#define TRACE_Y       52
#define TRACE_W       800
#define TRACE_H       224
#define TRACE_GAP     20           // blank columns ahead of the write head

#define SPEC_X        0
#define SPEC_Y        284
// 400 px, not 800: this canvas is fully rewritten every ~5 s, and at 800 wide
// that was 166 KB of PSRAM churn -- the only thing added since the build that
// was glitch-free. 0-50 Hz still fits, at 2 px per FFT bin instead of 4.
#define SPEC_W        400
#define SPEC_H        104
// The dB window is ADAPTIVE. A fixed -6..+34 dB re 1 uV was a guess and it was
// wrong: with rms of a few uV spread over 128 bins, individual bins sit near
// -30 dB, so every bar clamped to zero height and the panel rendered blank.
// Track the observed floor and peak instead, slowly, so the display self-tunes
// to whatever the station is actually doing.
static float spec_lo = -40.0f, spec_hi = 0.0f;
// Seconds of ground motion per pixel column. This is the ONE number that decides
// whether the display reads as live or as a chart recorder:
//   0.05  -> 20 px/s, 40 s across the screen   (live scroller -- what a demo wants)
//   1.0   ->  1 px/s, 13.3 min across          (wall helicorder -- looks frozen)
// /v1/live carries 30 s of history, so at 0.05 the first poll fills 600 of the
// 800 columns immediately instead of drawing a 30 px stub.
#define COL_PERIOD_S  0.05

static lv_obj_t *canvas, *spec_canvas;
static lv_obj_t *lbl_title, *lbl_stats, *lbl_net, *lbl_ev[3], *lbl_peak;
static lv_color16_t *canvas_buf, *spec_buf;

// Completed columns wait here instead of being drawn immediately. A fetch
// delivers ~5 s of samples at once, which at COL_PERIOD_S is ~100 columns --
// drawn in one pass that is a ~45 KB invalidate, i.e. exactly the burst that
// desyncs the scanout. The queue turns that burst into a steady trickle.
#define COLQ_N  512
struct ColQ { float mn, mx; };
static ColQ    colq[COLQ_N];
static uint16_t colq_head = 0, colq_tail = 0;
#define COLQ_PER_FRAME 4          // ~1.8 KB/frame, 120 col/s at 30 Hz -- ample

static inline void colq_push(float mn, float mx)
{
    const uint16_t nxt = (colq_head + 1) % COLQ_N;
    if (nxt == colq_tail) colq_tail = (colq_tail + 1) % COLQ_N;  // drop oldest
    colq[colq_head].mn = mn; colq[colq_head].mx = mx;
    colq_head = nxt;
}

// rolling window feeding the FFT
static float  fft_ring[FFT_N];
static size_t fft_head = 0;
static bool   fft_ready = false;
static float  peak_uv_boot = 0.0f;   // "biggest since you plugged it in"

// There is no RTC on this board, but /v1/live's t_end IS Unix epoch, so the
// server's clock is delivered on every fetch. Hold it and tick forward with
// millis() in between. Accuracy is pi5's clock plus a few hundred ms of poll
// latency -- fine for reading a detection list, not for picking arrivals.
static double   epoch_ref = 0;
static uint32_t epoch_ref_ms = 0;
static lv_obj_t *lbl_clock;

static double utc_now(void)
{
    if (epoch_ref <= 0) return 0;
    return epoch_ref + (double)(millis() - epoch_ref_ms) / 1000.0;
}

// ------------------------------------------------------------ trace state --
static int32_t  col = 0;           // current column
static int64_t  col_epoch = 0;     // absolute second this column represents
static float    col_min = 0, col_max = 0;
static bool     col_open = false;
static double   last_sample_t = 0; // newest sample time already consumed
static float    scale_ema = 20.0f; // µV mapping to the auto-scale reference

static inline lv_color16_t rgb565(uint8_t r, uint8_t g, uint8_t b)
{
    lv_color16_t c;
    c.red = r >> 3; c.green = g >> 2; c.blue = b >> 3;
    return c;
}

static const lv_color16_t COL_BG   = rgb565(0x08, 0x0A, 0x0C);
static const lv_color16_t COL_GRID = rgb565(0x20, 0x28, 0x30);
static const lv_color16_t COL_WAVE = rgb565(0x30, 0xE0, 0x60);
static const lv_color16_t COL_HOT  = rgb565(0xFF, 0x60, 0x40);
static const lv_color16_t COL_SPEC = rgb565(0x40, 0xB8, 0xFF);
static const lv_color16_t COL_MARK = rgb565(0x60, 0x50, 0x30);   // known-line markers

// Draw one column. min/max are µV; the column is the helicorder envelope for
// that second, which is the only honest reduction when 100 samples share one
// pixel -- a decimation would alias away exactly the spikes we care about.
static void draw_column(int32_t x, float vmin, float vmax)
{
    const int32_t mid = TRACE_H / 2;

    const float amp = fmaxf(fabsf(vmin), fabsf(vmax));
    scale_ema = 0.99f * scale_ema + 0.01f * amp;
    const float ref = fmaxf(scale_ema, 1.0f);
    const float px_per_uv = (TRACE_H * 0.16f) / ref;

    int32_t y0 = mid - (int32_t)(vmax * px_per_uv);
    int32_t y1 = mid - (int32_t)(vmin * px_per_uv);
    if (y0 > y1) { const int32_t t = y0; y0 = y1; y1 = t; }
    const bool clipped = (y0 < 0) || (y1 >= TRACE_H);
    if (y0 < 0) y0 = 0;
    if (y1 >= TRACE_H) y1 = TRACE_H - 1;

    // Enqueue background, centre line, then the waveform on top. FIFO order is
    // the paint order, so the last one wins where they overlap.
    paint_rect(0, (int16_t)x, 0, 1, TRACE_H, COL_BG);
    paint_rect(0, (int16_t)x, (int16_t)mid, 1, 1, COL_GRID);
    paint_vline(0, (int16_t)x, (int16_t)y0, (int16_t)y1, clipped ? COL_HOT : COL_WAVE);

    // Blank gap ahead of the write head, maintained incrementally: only the one
    // column newly entering the gap is cleared.
    const int32_t xg = (x + TRACE_GAP) % TRACE_W;
    paint_rect(0, (int16_t)xg, 0, 1, TRACE_H, COL_BG);
    paint_rect(0, (int16_t)xg, (int16_t)mid, 1, 1, COL_GRID);
}

// The station's documented spectral lines (CLAUDE.md). Drawn as faint vertical
// markers so the display teaches what the peaks ARE rather than showing an
// anonymous forest: 41 / 40.6 / 37.65 Hz are the heat-pump AC, 40.0 Hz is the
// 60 Hz mains alias at 100 sps, 19.3 / 20 Hz the HVAC's evening high stage, and
// 1.05 Hz is still unexplained.
static const float KNOWN_LINES[] = {1.05f, 19.3f, 20.0f, 37.65f, 40.0f, 40.6f, 41.0f};

static void spectrum_compute(float fs)
{
    if (!spec_buf || !fft_ready)
    {
        log_w("spec: skipped (buf=%p ready=%d)", spec_buf, (int)fft_ready);
        return;
    }

    static float win[FFT_N], db[FFT_BINS];
    for (int i = 0; i < FFT_N; i++)
        win[i] = fft_ring[(fft_head + i) % FFT_N];
    spectrum_db(win, db);

    // Observed range this frame, ignoring DC in bin 0.
    float lo = 1e9f, hi = -1e9f;
    for (int k = 1; k < FFT_BINS; k++)
    {
        if (db[k] < lo) lo = db[k];
        if (db[k] > hi) hi = db[k];
    }
    if (hi - lo < 12.0f) hi = lo + 12.0f;      // never amplify a flat spectrum
    spec_lo = 0.9f * spec_lo + 0.1f * lo;
    spec_hi = 0.9f * spec_hi + 0.1f * (hi + 3.0f);

    const float hz_per_bin = fs / FFT_N;
    const float nyquist    = fs * 0.5f;
    const float span       = (spec_hi - spec_lo) > 1.0f ? (spec_hi - spec_lo) : 1.0f;

    for (int32_t x = 0; x < SPEC_W; x++)
    {
        const float hz  = (float)x / (SPEC_W - 1) * nyquist;
        const int   bin = (int)(hz / hz_per_bin + 0.5f);
        const float v   = db[bin < FFT_BINS ? bin : FFT_BINS - 1];

        float frac = (v - spec_lo) / span;
        if (frac < 0) frac = 0;
        if (frac > 1) frac = 1;
        const int16_t top = (int16_t)(SPEC_H - 1 - (int32_t)(frac * (SPEC_H - 1)));

        bool marked = false;
        for (unsigned m = 0; m < sizeof KNOWN_LINES / sizeof KNOWN_LINES[0]; m++)
            if (fabsf(hz - KNOWN_LINES[m]) < hz_per_bin * 0.6f) { marked = true; break; }

        // Just enqueue. The drainer decides when this reaches PSRAM.
        if (top > 0) paint_rect(1, (int16_t)x, 0, 1, top, marked ? COL_MARK : COL_BG);
        paint_rect(1, (int16_t)x, top, 1, (int16_t)(SPEC_H - top), COL_SPEC);
    }
}

// Feed one sample, at absolute time t, into the current column bin.
static void feed(double t, float uv)
{
    fft_ring[fft_head] = uv;
    fft_head = (fft_head + 1) % FFT_N;
    if (fft_head == 0) fft_ready = true;
    if (fabsf(uv) > peak_uv_boot) peak_uv_boot = fabsf(uv);

    const int64_t sec = (int64_t)(t / COL_PERIOD_S);

    if (!col_open)
    {
        col_epoch = sec; col_min = col_max = uv; col_open = true;
        return;
    }
    if (sec == col_epoch)
    {
        if (uv < col_min) col_min = uv;
        if (uv > col_max) col_max = uv;
        return;
    }

    colq_push(col_min, col_max);

    // A gap (missed polls) must advance the cursor, not compress time.
    for (int64_t g = col_epoch + 1; g < sec && g < col_epoch + TRACE_W; g++)
        colq_push(0.0f, 0.0f);
    col_epoch = sec; col_min = col_max = uv;
}

// ---------------------------------------------------------------- fetch -----
// Read the WHOLE body, then parse it. An earlier version streamed the array off
// the socket to keep memory O(1); that was premature optimisation -- 20 KB
// against ~130 KB of free internal heap was never the constraint -- and it cost
// three bugs, the worst of which abandoned half-read sockets and pinned server
// threads against seismo_server.py's listen backlog of 5.
static bool fetch_live()
{
    if (WiFi.status() != WL_CONNECTED)
        return false;

    HTTPClient http;
    char url[128];
    snprintf(url, sizeof url, "http://%s:%d/v1/live", SEISMO_HOST, SEISMO_PORT);
    http.setConnectTimeout(4000);
    http.setTimeout(8000);
    // seismo_server.py is BaseHTTPRequestHandler: HTTP/1.0, closes after every
    // response. HTTPClient defaults to keep-alive and would reuse a dead socket.
    http.setReuse(false);
    if (!http.begin(url)) return false;

    const int code = http.GET();
    if (code != 200) { http.end(); log_w("/v1/live -> HTTP %d", code); return false; }

    String body = http.getString();   // reads to Content-Length, then closes cleanly
    http.end();
    if (body.length() < 32) { log_w("/v1/live: short body %d", body.length()); return false; }

    double t_end = 0, fs = 100.0, rms = 0, age = 0;
    int i;
    // atof skips leading whitespace, so `"fs": 100.0` parses as happily as `"fs":100.0`
    if ((i = body.indexOf("\"t_end\":")) >= 0) t_end = atof(body.c_str() + i + 8);
    if ((i = body.indexOf("\"fs\":"))    >= 0) fs    = atof(body.c_str() + i + 5);
    if ((i = body.indexOf("\"rms\":"))   >= 0) rms   = atof(body.c_str() + i + 6);
    if ((i = body.indexOf("\"age\":"))   >= 0) age   = atof(body.c_str() + i + 6);

    const int a = body.indexOf("\"uv\":");
    if (a < 0 || t_end <= 0 || fs <= 0) { log_w("/v1/live: missing uv/t_end/fs"); return false; }
    int p = body.indexOf('[', a);
    if (p < 0) return false;
    const int q = body.indexOf(']', p);
    if (q < 0) return false;

    // Count first so samples can be timestamped backwards from t_end.
    size_t n = 0;
    for (int k = p + 1; k < q; k++) if (body[k] == ',') n++;
    n += 1;

    const double t0 = t_end - (double)(n - 1) / fs;
    size_t used = 0, idx = 0;
    const char *c = body.c_str() + p + 1;
    const char *stop = body.c_str() + q;
    while (c < stop && idx < n)
    {
        char *nxt;
        const float uv = strtof(c, &nxt);
        if (nxt == c) break;
        const double t = t0 + (double)idx / fs;
        if (t > last_sample_t) { feed(t, uv); last_sample_t = t; used++; }
        idx++;
        c = nxt;
        while (c < stop && (*c == ',' || *c == ' ')) c++;
    }

    // NOT lv_label_set_text_fmt: LVGL's built-in printf is compiled without
    // float support, so "%.1f" emits a literal "f" and every later argument
    // shifts. Every number on the display was wrong. Use newlib's snprintf.
    {
        char buf[96];
        snprintf(buf, sizeof buf, "rms %.1f uV   age %.1f s   +%u", rms, age, (unsigned)used);
        lv_label_set_text(lbl_stats, buf);
    }
    epoch_ref = t_end; epoch_ref_ms = millis();
    log_i("live: n=%u used=%u col=%d t_end=%.1f", (unsigned)n, (unsigned)used, (int)col, t_end);
    return used > 0;    // "productive?", so the caller can pace itself
}

// ---------------------------------------------------------------- events ----
// /v1/events returns a bare JSON list, newest first. Shown because a helicorder
// alone cannot tell you whether the station is DOING anything -- the detector's
// own verdict is the interesting part, and peak_ratio is the STA/LTA that fired.
static void fetch_events()
{
    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;
    char url[160];
    snprintf(url, sizeof url, "http://%s:%d/v1/events?limit=3", SEISMO_HOST, SEISMO_PORT);
    http.setConnectTimeout(4000);
    http.setTimeout(8000);
    http.setReuse(false);
    if (!http.begin(url)) return;
    if (http.GET() != 200) { http.end(); return; }
    String body = http.getString();
    http.end();

    int at = 0;
    for (int row = 0; row < 3; row++)
    {
        const int ob = body.indexOf('{', at);
        if (ob < 0) { lv_label_set_text(lbl_ev[row], ""); continue; }
        const int oe = body.indexOf('}', ob);
        if (oe < 0) { lv_label_set_text(lbl_ev[row], ""); continue; }
        String o = body.substring(ob, oe);
        at = oe + 1;

        int i;
        double dur = 0, ratio = 0, puv = 0, hflf = 0;
        if ((i = o.indexOf("\"duration_s\":")) >= 0) dur   = atof(o.c_str() + i + 13);
        if ((i = o.indexOf("\"peak_ratio\":")) >= 0) ratio = atof(o.c_str() + i + 13);
        if ((i = o.indexOf("\"peak_uv\":"))    >= 0) puv   = atof(o.c_str() + i + 10);
        if ((i = o.indexOf("\"hf_lf\":"))      >= 0) hflf  = atof(o.c_str() + i + 8);

        // start is ISO-8601 in UTC; take HH:MM:SS. No RTC on this board, so we
        // show the server's UTC verbatim rather than pretending to localise it.
        String hhmmss = "--:--:--";
        if ((i = o.indexOf("\"start\":")) >= 0)
        {
            const int qs = o.indexOf('"', i + 8);
            if (qs > 0 && o.length() > (unsigned)(qs + 20)) hhmmss = o.substring(qs + 12, qs + 20);
        }
        {
            char buf[128];
            snprintf(buf, sizeof buf, "%s UTC   %5.1f uV   x%.1f   %.1f s   hf/lf %.1f",
                     hhmmss.c_str(), puv, ratio, dur, hflf);
            lv_label_set_text(lbl_ev[row], buf);
        }
        lv_obj_set_style_text_color(lbl_ev[row],
            lv_color_hex(ratio >= 8.0 ? 0xFFC040 : 0x8FA0AC), LV_PART_MAIN);
    }
}

// ---------------------------------------------------------------- setup -----
void setup()
{
    Serial.begin(115200);
    smartdisplay_init();
    smartdisplay_lcd_set_backlight(1.0f);

    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x080A0C), LV_PART_MAIN);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    // ---- header ----
    lbl_title = lv_label_create(scr);
    lv_label_set_text(lbl_title, "SS.OAKM1.00.EHZ");
    lv_obj_set_style_text_color(lbl_title, lv_color_hex(0xE8EEF2), LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_title, &lv_font_montserrat_28, LV_PART_MAIN);
    lv_obj_align(lbl_title, LV_ALIGN_TOP_LEFT, 12, 6);

    lv_obj_t *sub = lv_label_create(scr);
    lv_label_set_text(sub, "Oakmont, Sonoma County  -  4.5 Hz vertical geophone");
    lv_obj_set_style_text_color(sub, lv_color_hex(0x6C7A85), LV_PART_MAIN);
    lv_obj_align(sub, LV_ALIGN_TOP_LEFT, 250, 16);

    lbl_net = lv_label_create(scr);
    lv_label_set_text(lbl_net, "wifi...");
    lv_obj_set_style_text_color(lbl_net, lv_color_hex(0x6C7A85), LV_PART_MAIN);
    lv_obj_align(lbl_net, LV_ALIGN_TOP_RIGHT, -12, 8);

    lbl_clock = lv_label_create(scr);
    lv_label_set_text(lbl_clock, "--:--:-- UTC");
    lv_obj_set_style_text_color(lbl_clock, lv_color_hex(0xE8EEF2), LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_clock, &lv_font_montserrat_28, LV_PART_MAIN);
    lv_obj_align(lbl_clock, LV_ALIGN_TOP_MID, 40, 6);

    lbl_stats = lv_label_create(scr);
    lv_label_set_text(lbl_stats, "connecting to pi5...");
    lv_obj_set_style_text_color(lbl_stats, lv_color_hex(0x30E060), LV_PART_MAIN);
    lv_obj_align(lbl_stats, LV_ALIGN_TOP_RIGHT, -12, 26);

    // ---- helicorder canvas ----
    canvas_buf = (lv_color16_t *)heap_caps_malloc(
        TRACE_W * TRACE_H * sizeof(lv_color16_t), MALLOC_CAP_SPIRAM);
    if (canvas_buf)
    {
        canvas = lv_canvas_create(scr);
        lv_canvas_set_buffer(canvas, canvas_buf, TRACE_W, TRACE_H, LV_COLOR_FORMAT_RGB565);
        lv_obj_set_pos(canvas, TRACE_X, TRACE_Y);
        for (int32_t y = 0; y < TRACE_H; y++)
            for (int32_t x = 0; x < TRACE_W; x++)
                canvas_buf[y * TRACE_W + x] = (y == TRACE_H / 2) ? COL_GRID : COL_BG;
        paint_register(0, canvas, canvas_buf, TRACE_W, TRACE_H);
    }
    else Serial.println("FATAL: trace canvas would not allocate");

    // ---- spectrum canvas ----
    spec_buf = (lv_color16_t *)heap_caps_malloc(
        SPEC_W * SPEC_H * sizeof(lv_color16_t), MALLOC_CAP_SPIRAM);
    if (spec_buf)
    {
        spec_canvas = lv_canvas_create(scr);
        lv_canvas_set_buffer(spec_canvas, spec_buf, SPEC_W, SPEC_H, LV_COLOR_FORMAT_RGB565);
        lv_obj_set_pos(spec_canvas, SPEC_X, SPEC_Y);
        for (int32_t i = 0; i < SPEC_W * SPEC_H; i++) spec_buf[i] = COL_BG;
        paint_register(1, spec_canvas, spec_buf, SPEC_W, SPEC_H);
    }
    else Serial.println("FATAL: spectrum canvas would not allocate");

    lv_obj_t *spl = lv_label_create(scr);
    lv_label_set_text(spl, "SPECTRUM 0-50 Hz   markers: 1.05 / 19.3 / 20 / 37.65 / 40 / 40.6 / 41 Hz");
    lv_obj_set_style_text_color(spl, lv_color_hex(0x5A6871), LV_PART_MAIN);
    lv_obj_align(spl, LV_ALIGN_TOP_LEFT, 12, SPEC_Y - 16);

    // ---- event strip ----
    lv_obj_t *evh = lv_label_create(scr);
    lv_label_set_text(evh, "RECENT DETECTIONS");
    lv_obj_set_style_text_color(evh, lv_color_hex(0x5A6871), LV_PART_MAIN);
    lv_obj_align(evh, LV_ALIGN_TOP_LEFT, 12, SPEC_Y + SPEC_H + 6);

    for (int i = 0; i < 3; i++)
    {
        lbl_ev[i] = lv_label_create(scr);
        lv_label_set_text(lbl_ev[i], "");
        lv_obj_set_style_text_color(lbl_ev[i], lv_color_hex(0x8FA0AC), LV_PART_MAIN);
        lv_obj_align(lbl_ev[i], LV_ALIGN_TOP_LEFT, 12, SPEC_Y + SPEC_H + 24 + i * 18);
    }

    lbl_peak = lv_label_create(scr);
    lv_label_set_text(lbl_peak, "");
    lv_obj_set_style_text_color(lbl_peak, lv_color_hex(0xFFC040), LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_peak, &lv_font_montserrat_24, LV_PART_MAIN);
    lv_obj_align(lbl_peak, LV_ALIGN_BOTTOM_RIGHT, -12, -14);

#ifdef DEMO_NO_WIFI
    // A/B control: everything above is identical, the radio is never brought up
    // and samples are synthesised. Isolates "does WiFi cause the glitching".
    Serial.println("\n=== NO-WIFI CONTROL BUILD: synthetic samples ===");
    lv_label_set_text(lbl_net, "radio off (control build)");
#else
    // Bandwidth was measured here once and the numbers are in README.md:
    //   PSRAM read 25.3 / write 35.5 MB/s, SRAM read 47.8, SRAM->PSRAM 28.6 MB/s,
    //   against 15.4 MB/s of continuous scanout at 20 fps.
    // The benchmark is GONE rather than #ifdef'd: it needed a 48 KB static
    // buffer in internal SRAM, and that starved WiFi's own internal allocations
    // badly enough that the radio stopped associating.
    Serial.printf("internal heap: %u free, %u largest block\n",
                  (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                  (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));

    Serial.printf("\n=== live helicorder: %s:%d ===\n", SEISMO_HOST, SEISMO_PORT);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
#endif
}

void loop()
{
    static uint32_t last = millis(), last_poll = 0, last_net = 0;
    const uint32_t now = millis();
    lv_tick_inc(now - last);
    last = now;

#ifdef DEMO_NO_WIFI
    // Feed synthetic ground motion at the same 100 sps and in the same 5 s
    // blocks pi5 delivers, so the drawing load matches the live build exactly.
    {
        static double t = 1.0e6;
        static uint32_t last_block = 0;
        if (now - last_block >= 4000)
        {
            last_block = now;
            static float ph = 0;
            for (int i = 0; i < 500; i++)          // 5 s at 100 sps
            {
                ph += 0.06f;
                const float uv = 18.0f * sinf(ph) * (0.3f + fabsf(sinf(ph * 0.017f)))
                               + 6.0f * sinf(ph * 7.3f);
                feed(t, uv);
                t += 0.01;
            }
            spectrum_compute(100.0f);
            {
                char buf[64];
                snprintf(buf, sizeof buf, "peak since boot  %.0f uV", peak_uv_boot);
                lv_label_set_text(lbl_peak, buf);
            }
        }
    }
    for (int k = 0; k < COLQ_PER_FRAME && colq_tail != colq_head; k++)
    {
        draw_column(col, colq[colq_tail].mn, colq[colq_tail].mx);
        col = (col + 1) % TRACE_W;
        colq_tail = (colq_tail + 1) % COLQ_N;
    }
    lv_timer_handler();
    delay(30);
    return;
#endif

    if (now - last_net >= 1000)
    {
        last_net = now;
        const bool up = WiFi.status() == WL_CONNECTED;

        // one-shot network dump: which subnet did we actually land on?
        static bool dumped = false;
        if (up && !dumped)
        {
            dumped = true;
            Serial.printf("NET ip=%s  mask=%s  gw=%s  dns=%s  rssi=%d  ssid=%s\n",
                          WiFi.localIP().toString().c_str(),
                          WiFi.subnetMask().toString().c_str(),
                          WiFi.gatewayIP().toString().c_str(),
                          WiFi.dnsIP().toString().c_str(),
                          WiFi.RSSI(), WiFi.SSID().c_str());

            // raw TCP reachability, separate from HTTPClient's error codes
            WiFiClient probe;
            const uint32_t t0 = millis();
            const int ok = probe.connect(SEISMO_HOST, SEISMO_PORT, 4000);
            Serial.printf("TCP %s:%d -> %s (%lu ms)\n", SEISMO_HOST, SEISMO_PORT,
                          ok ? "OPEN" : "REFUSED/TIMEOUT", (unsigned long)(millis() - t0));
            probe.stop();

            // is the gateway itself reachable? separates "no route" from "host blocked"
            WiFiClient gw;
            const bool gwok = gw.connect(WiFi.gatewayIP(), 80, 2000);
            Serial.printf("TCP gateway:80 -> %s\n", gwok ? "OPEN" : "no");
            gw.stop();
        }
        static bool last_up = false;
        static uint32_t ticks = 0;
        if (up)
        {
            const String ip = WiFi.localIP().toString();
            lv_label_set_text_fmt(lbl_net, "%s  %d dBm", ip.c_str(), WiFi.RSSI());
            if (!last_up) log_i("wifi up: %s  %d dBm", ip.c_str(), WiFi.RSSI());
        }
        else
        {
            lv_label_set_text(lbl_net, "wifi: connecting");
            log_w("net label -> 'wifi: connecting'  (WiFi.status()=%d)", (int)WiFi.status());
        }
        last_up = up; ticks++;

        const double u = utc_now();
        if (u > 0)
        {
            const time_t tt = (time_t)u;
            struct tm g;
            gmtime_r(&tt, &g);
            char cbuf[32];
            snprintf(cbuf, sizeof cbuf, "%02d:%02d:%02d UTC", g.tm_hour, g.tm_min, g.tm_sec);
            lv_label_set_text(lbl_clock, cbuf);
        }
    }

    // Adaptive poll. pi5 refreshes the live window in ~5.5 s blocks, so a fixed
    // 2 s poll spent half its fetches pulling 20 KB (and a server thread) to
    // learn t_end had not moved. Back off after a productive fetch, close in
    // after a barren one. /v1/live carries 30 s of history, so being late costs
    // nothing -- we just consume more samples next time.
    static uint32_t poll_gap = 2000;
    if (now - last_poll >= poll_gap)
    {
        last_poll = now;
        const bool got = fetch_live();
        poll_gap = got ? 4000 : 1500;
        if (got)
        {
            // Repainting the spectrum is 166 KB. Only ever do it when there is
            // new data -- ~0.2 Hz -- never per frame. See README on desync.
            spectrum_compute(100.0f);   // queues the repaint; painting is paced below
            {
                char buf[64];
                snprintf(buf, sizeof buf, "peak since boot  %.0f uV", peak_uv_boot);
                lv_label_set_text(lbl_peak, buf);
            }
        }
    }

    // drain the column queue a few at a time -- never a burst
    for (int k = 0; k < COLQ_PER_FRAME && colq_tail != colq_head; k++)
    {
        draw_column(col, colq[colq_tail].mn, colq[colq_tail].mx);
        col = (col + 1) % TRACE_W;
        colq_tail = (colq_tail + 1) % COLQ_N;
    }

    // NO periodic esp_lcd_rgb_panel_restart() here. Restarting DMA disrupts a
    // frame, so calling it on a timer injects a glitch every interval by design.
    // CONFIG_LCD_RGB_RESTART_IN_VSYNC (=1 in this framework) already restarts
    // automatically, and only when the hardware has actually desynced.
    // display_restart_panel() remains available as a manual lever.


    // detections change slowly; 20 s is plenty and keeps pi5 quiet
    static uint32_t last_ev = 0;
    if (now - last_ev >= 20000) { last_ev = now; fetch_events(); }

    // Align all drawing to the vertical blanking interval. The RGB peripheral
    // fetches no framebuffer data during blanking, and our porch is 484 lines
    // against 480 active, so ~half of every frame the PSRAM bus is ours alone.
    // This also paces the loop at exactly the panel rate, which is why there is
    // no delay() here -- rendering faster than the panel refreshes is invisible
    // work that only steals bandwidth.
    if (!display_wait_vsync(100))
        delay(30);          // IDF 4.4 build, or vsync not available: fall back

    // Inside the blanking window the PSRAM bus is ours. Drain the paint queue
    // up to a per-frame pixel budget: 800 x 60 px = 96 KB, ~3.4 ms of flush at
    // the measured 28.6 MB/s, comfortably inside the ~25 ms of blanking. Work
    // that does not fit simply lands next frame -- "as fast as possible, but no
    // faster", which is the whole point of the queue.
    paint_drain(800 * 60);
    lv_timer_handler();
}
