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
#include "ui_shell.h"
#include "weather.h"

// ---------------------------------------------------------------- geometry --
// Each page owns the whole content area now (720 x 428), so nothing has to
// share. Sizes are computed from the shell rather than hard-coded to 800x480,
// which is what makes the shell reusable on a different panel.
#define TRACE_X       0
#define TRACE_Y       52
#define TRACE_AX_W    52         // left gutter for the y-axis labels
#define TRACE_W       663        // 720 - gutter - 5 px right margin
#define TRACE_H       340
#define TRACE_GAP     20           // blank columns ahead of the write head

#define SPEC_X        0
#define SPEC_Y        284
// 400 px, not 800: this canvas is fully rewritten every ~5 s, and at 800 wide
// that was 166 KB of PSRAM churn -- the only thing added since the build that
// was glitch-free. 0-50 Hz still fits, at 2 px per FFT bin instead of 4.
#define SPEC_W        715        // ditto -- do not run to the right edge
#define SPEC_H        300
// The dB window is ADAPTIVE. A fixed -6..+34 dB re 1 uV was a guess and it was
// wrong: with rms of a few uV spread over 128 bins, individual bins sit near
// -30 dB, so every bar clamped to zero height and the panel rendered blank.
// Track the observed floor and peak instead, slowly, so the display self-tunes
// to whatever the station is actually doing.
static float spec_lo = -40.0f, spec_hi = 0.0f;
// Seconds of ground motion per pixel column. This is the ONE number that decides
// whether the display reads as live or as a chart recorder:
//   0.02  -> 50 px/s, 14.3 s across   ~2 samples/px: the envelope IS the waveform
//   0.05  -> 20 px/s, 36 s across      ~5 samples/px: adjacent columns merge into
//                                      a solid slab with no visible texture
//   1.0   ->  1 px/s, 13.3 min across  (wall helicorder -- looks frozen live)
// The web dashboard draws ~1.5 px per sample, which is why it shows individual
// oscillations. Below ~1 sample/px a min/max fill is the honest rendering but
// destroys all texture -- the density, not the colour, is what makes it dull.
// /v1/live carries 30 s of history, so at 0.05 the first poll fills 600 of the
// 800 columns immediately instead of drawing a 30 px stub.
#define COL_PERIOD_S  0.02

static lv_obj_t *canvas, *spec_canvas;
static lv_obj_t *lbl_stats, *lbl_ev[3];
static lv_color16_t *canvas_buf, *spec_buf;

// Completed columns wait here instead of being drawn immediately. A fetch
// delivers ~5 s of samples at once, which at COL_PERIOD_S is ~100 columns --
// drawn in one pass that is a ~45 KB invalidate, i.e. exactly the burst that
// desyncs the scanout. The queue turns that burst into a steady trickle.
#define COLQ_N  1024
struct ColQ { float mn, mx; };
static ColQ    colq[COLQ_N];
static uint16_t colq_head = 0, colq_tail = 0;
static size_t   colq_depth = 0;
// PLAYOUT BUFFER. Data arrives in bursts -- ~263 columns every ~5 s -- so
// draining "as fast as possible" made the trace sprint across the screen and
// then sit still for four seconds. Smoothness does not come from draining
// faster; it comes from draining at exactly the rate the data was RECORDED,
// with a cushion deep enough to ride out the burstiness. Same idea as an audio
// or video jitter buffer.
//
// Nominal rate is one column per COL_PERIOD_S of real time. A slow servo
// nudges it either side of nominal to hold the buffer near COLQ_TARGET, so a
// slightly fast or slow feed is absorbed rather than accumulating.
//
// The cost is latency, and it is worth stating plainly: the display sits
// COLQ_TARGET * COL_PERIOD_S behind the feed -- about 6 s here, on top of the
// ~4 s feed age. For a wall display that is a good trade for smooth motion; it
// would be the wrong trade for anything you were trying to react to.
#define COLQ_TARGET   300         // ~6 s of cushion at 0.02 s/column
#define COLQ_SERVO    0.5f        // how hard to correct toward the target

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
static float  last_rms = 0, last_age = 0;

// There is no RTC on this board, but /v1/live's t_end IS Unix epoch, so the
// server's clock is delivered on every fetch. Hold it and tick forward with
// millis() in between. Accuracy is pi5's clock plus a few hundred ms of poll
// latency -- fine for reading a detection list, not for picking arrivals.
static double   epoch_ref = 0;
static uint32_t epoch_ref_ms = 0;


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
static const lv_color16_t COL_GRID = rgb565(0x3E, 0x4C, 0x58);   // decade lines
static const lv_color16_t COL_AXIS = rgb565(0x5A, 0x6E, 0x7C);   // zero line
static const lv_color16_t COL_WAVE = rgb565(0x30, 0xE0, 0x60);
static const lv_color16_t COL_HOT  = rgb565(0xFF, 0x60, 0x40);
static const lv_color16_t COL_SPEC = rgb565(0x40, 0xB8, 0xFF);
static const lv_color16_t COL_MARK = rgb565(0x4A, 0x3E, 0x22);   // known-line wash
static const lv_color16_t COL_TICK = rgb565(0xFF, 0xC0, 0x40);   // known-line tick

// Draw one column. min/max are µV; the column is the helicorder envelope for
// that second, which is the only honest reduction when 100 samples share one
// pixel -- a decimation would alias away exactly the spikes we care about.
// Microvolts -> signed pixel offset, logarithmic, fixed scale.
#define TRACE_UV0    0.5f                     // the "zero" of the log scale
#define TRACE_DEC_PX 39.0f                    // pixels per decade of uV
static inline float uv_to_px(float uv)
{
    const float a = fabsf(uv);
    float p = TRACE_DEC_PX * log10f(1.0f + a / TRACE_UV0);
    const float lim = TRACE_H / 2 - 2;
    if (p > lim) p = lim;
    return (uv < 0) ? -p : p;
}

static int32_t decade_px[4];      // pixel offsets of 1/10/100/1000 uV, set in setup

// AMPLITUDE COLOUR BANDS.
//
// On a log trace the row already encodes amplitude, so colour can be a pure
// function of distance from the centre line -- computed once here, not per
// sample. At a glance: all green is a quiet night, yellow is something worth
// looking at, red is big.
//
// Thresholds are chosen against this station's own numbers: the noise floor is
// ~0.8 uV quiet / ~3.5 uV afternoon, so "green" is normal life; 10-100 uV is
// footsteps, doors and traffic; past 100 uV is rare, and the M3.3 felt in the
// house on 2026-09-03 reached 6843 uV.
struct AmpBand { float uv_hi; lv_color16_t c; };
static const AmpBand AMP_BANDS[] = {
    {  10.0f, rgb565(0x5C, 0xE0, 0x3C) },   // green   - normal, ONE colour
    {  30.0f, rgb565(0xC6, 0xE8, 0x28) },   // lime    - something moved
    { 100.0f, rgb565(0xFF, 0xD4, 0x2E) },   // yellow  - hmm
    { 300.0f, rgb565(0xFF, 0x93, 0x1E) },   // orange  - unusual
    { 1e9f,   rgb565(0xFF, 0x3C, 0x2E) },   // red     - uh-oh
};
// Deliberately ONE green below 10 uV. Splitting it at 3 uV made every quiet
// column dark at the base and bright at the tip -- it looked like new growth on
// a plant, and implied a distinction that does not exist. Both shades meant
// "normal". Colour changes should mark a change of meaning, not of magnitude
// within the same meaning.
#define N_AMP_BANDS (sizeof AMP_BANDS / sizeof AMP_BANDS[0])

static int32_t band_px[N_AMP_BANDS];      // outer edge of each band, in pixels

static void draw_column(int32_t x, float vmin, float vmax)
{
    const int32_t mid = TRACE_H / 2;

    // LOG amplitude, FIXED calibration. Auto-scaling to fill the panel made a
    // passing truck and a felt earthquake look identical -- it told the viewer
    // that all ground motion is equally dramatic, which is a lie. This maps a
    // constant number of pixels per DECADE of microvolts, so quiet nights look
    // quiet and a real event is unmistakable, across the four orders of
    // magnitude between the 0.8 uV noise floor and the 6843 uV M3.3 of 09-03.
    //
    //   1 uV -> 19 px      100 uV ->  90 px
    //   5 uV -> 41 px     6843 uV -> 161 px (near full scale)
    int32_t y0 = mid - (int32_t)uv_to_px(vmax);
    int32_t y1 = mid - (int32_t)uv_to_px(vmin);
    if (y0 > y1) { const int32_t t = y0; y0 = y1; y1 = t; }
    const bool clipped = (fabsf(vmin) > 8000.0f) || (fabsf(vmax) > 8000.0f);
    if (y0 < 0) y0 = 0;
    if (y1 >= TRACE_H) y1 = TRACE_H - 1;

    // Enqueue background, centre line, then the waveform on top. FIFO order is
    // the paint order, so the last one wins where they overlap.
    paint_rect(0, (int16_t)x, 0, 1, TRACE_H, COL_BG);
    paint_rect(0, (int16_t)x, (int16_t)mid, 1, 1, COL_AXIS);
    // Decade gridlines, so the log scale is readable rather than mysterious.
    // Offsets are CONSTANT -- computed once, not with powf()/log10f() on every
    // column as they were. (A log lookup table is not needed: the only genuine
    // log calls left are two per column, ~50/s, which is free.)
    for (int d = 0; d < 4; d++)
    {
        paint_rect(0, (int16_t)x, (int16_t)(mid - decade_px[d]), 1, 1, COL_GRID);
        paint_rect(0, (int16_t)x, (int16_t)(mid + decade_px[d]), 1, 1, COL_GRID);
    }
    // Emit one rect per colour band the column actually crosses -- typically
    // two or three, not six, because a quiet column never leaves the green.
    for (unsigned b = 0; b < N_AMP_BANDS; b++)
    {
        const int32_t o_lo = (b == 0) ? 0 : band_px[b - 1];
        const int32_t o_hi = band_px[b];
        if (o_hi <= o_lo) continue;

        // rows above the centre line, then below
        int32_t a0 = mid - o_hi + 1, a1 = mid - o_lo;
        if (a0 < y0) a0 = y0;
        if (a1 > y1) a1 = y1;
        if (a1 >= a0) paint_rect(0, (int16_t)x, (int16_t)a0, 1,
                                 (int16_t)(a1 - a0 + 1), AMP_BANDS[b].c);

        int32_t b0 = mid + o_lo, b1 = mid + o_hi - 1;
        if (b0 < y0) b0 = y0;
        if (b1 > y1) b1 = y1;
        if (b1 >= b0) paint_rect(0, (int16_t)x, (int16_t)b0, 1,
                                 (int16_t)(b1 - b0 + 1), AMP_BANDS[b].c);
    }
    (void)clipped;

    // Blank gap ahead of the write head, maintained incrementally: only the one
    // column newly entering the gap is cleared.
    const int32_t xg = (x + TRACE_GAP) % TRACE_W;
    paint_rect(0, (int16_t)xg, 0, 1, TRACE_H, COL_BG);
    paint_rect(0, (int16_t)xg, (int16_t)mid, 1, 1, COL_AXIS);
    for (int d = 0; d < 4; d++)
    {
        paint_rect(0, (int16_t)xg, (int16_t)(mid - decade_px[d]), 1, 1, COL_GRID);
        paint_rect(0, (int16_t)xg, (int16_t)(mid + decade_px[d]), 1, 1, COL_GRID);
    }
}

// The station's documented spectral lines (CLAUDE.md). Drawn as faint vertical
// markers so the display teaches what the peaks ARE rather than showing an
// anonymous forest: 41 / 40.6 / 37.65 Hz are the heat-pump AC, 40.0 Hz is the
// 60 Hz mains alias at 100 sps, 19.3 / 20 Hz the HVAC's evening high stage, and
// 1.05 Hz is still unexplained.
// LOG frequency axis. On a linear 0-50 Hz axis the detection band (1-15 Hz) got
// the leftmost 30% of the panel while 60% went to 20-50 Hz, which is almost
// entirely cultural noise -- most of the display spent on the frequencies that
// matter least. Log gives 1-15 Hz about 60% of the width.
#define SPEC_F_LO   0.5f
#define SPEC_F_HI   50.0f
static inline float spec_x_to_hz(int32_t x)
{
    return SPEC_F_LO * powf(SPEC_F_HI / SPEC_F_LO, (float)x / (SPEC_W - 1));
}
static inline int32_t spec_hz_to_x(float hz)
{
    if (hz <= SPEC_F_LO) return 0;
    return (int32_t)((SPEC_W - 1) * logf(hz / SPEC_F_LO) / logf(SPEC_F_HI / SPEC_F_LO));
}

// Marker REGIONS, not seven identical ticks. 37.65/40/40.6/41 Hz span 3.35 Hz
// and cannot be told apart at any scaling on a 715 px full-range axis -- the FFT
// resolves them at 0.39 Hz bins, the display cannot. Shown as one labelled band
// for what they are, which is what a reader actually needs to know.
struct SpecRegion { float lo, hi; };
static const SpecRegion KNOWN_BANDS[] = {
    {1.02f,  1.09f},    // the unexplained instrumental line
    {19.1f, 20.2f},     // HVAC evening high stage
    {37.4f, 41.3f},     // heat-pump compressor + the 60 Hz mains alias at 40.0
};

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
    const float span       = (spec_hi - spec_lo) > 1.0f ? (spec_hi - spec_lo) : 1.0f;

    for (int32_t x = 0; x < SPEC_W; x++)
    {
        const float hz  = spec_x_to_hz(x);
        const int   bin = (int)(hz / hz_per_bin + 0.5f);
        const float v   = db[bin < FFT_BINS ? bin : FFT_BINS - 1];

        float frac = (v - spec_lo) / span;
        if (frac < 0) frac = 0;
        if (frac > 1) frac = 1;
        const int16_t top = (int16_t)(SPEC_H - 1 - (int32_t)(frac * (SPEC_H - 1)));

        bool marked = false;
        for (unsigned m = 0; m < sizeof KNOWN_BANDS / sizeof KNOWN_BANDS[0]; m++)
            if (hz >= KNOWN_BANDS[m].lo && hz <= KNOWN_BANDS[m].hi) { marked = true; break; }

        // Just enqueue. The drainer decides when this reaches PSRAM.
        if (top > 0) paint_rect(1, (int16_t)x, 0, 1, top, marked ? COL_MARK : COL_BG);
        paint_rect(1, (int16_t)x, top, 1, (int16_t)(SPEC_H - top), COL_SPEC);
        // Tick LAST and along the top edge, so it is drawn over the bar and
        // stays visible however tall the bar is. Marking only the region above
        // the bar hid the markers exactly at the peaks worth labelling.
        if (marked) paint_rect(1, (int16_t)x, 0, 1, 5, COL_TICK);
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
    if (sec > col_epoch + 1)
        log_w("trace gap: %d empty bins at t=%.3f (%.0f ms of missing samples)",
              (int)(sec - col_epoch - 1), t,
              (double)(sec - col_epoch - 1) * COL_PERIOD_S * 1000.0);
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
        // NOT the sample count: that was a debug counter (was the poll
        // productive?) and meant nothing to a viewer. The window span answers a
        // question the display otherwise leaves unanswered -- how much time is
        // on screen.
        snprintf(buf, sizeof buf,
                 "rms %.1f uV    delay %.0f s    %.0f s across",
                 rms, age + (double)colq_depth * COL_PERIOD_S,
                 (double)TRACE_W * COL_PERIOD_S);
        (void)used;
        lv_label_set_text(lbl_stats, buf);
    }
    // Anchor to NOW, not to the last sample. t_end is the timestamp of the
    // final sample in the window and the feed runs ~4 s behind real time, which
    // the server reports as `age`. Anchoring to t_end alone made the clock climb
    // between fetches and snap backwards on every new one. Never step backwards
    // either: prefer the later of the new estimate and what we are already
    // showing, unless the gap is big enough to be a genuine resync.
    {
        const double est = t_end + age;
        const double cur = utc_now();
        if (cur <= 0 || est > cur || (cur - est) > 3.0)
        {
            epoch_ref = est;
            epoch_ref_ms = millis();
        }
    }
    last_rms = (float)rms; last_age = (float)age;
    log_i("live: n=%u used=%u col=%d | paint pend=%u high=%u dropped=%lu | colq=%u",
          (unsigned)n, (unsigned)used, (int)col,
          (unsigned)paint_pending(), (unsigned)paint_high_water(),
          (unsigned long)paint_dropped(),
          (unsigned)((colq_head + COLQ_N - colq_tail) % COLQ_N));
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
static lv_obj_t *pg_trace, *pg_spec, *pg_info, *pg_wx;
static lv_obj_t *wx_now, *wx_detail, *wx_stamp;
static lv_obj_t *wx_day_lbl[WX_DAYS], *wx_day_temp[WX_DAYS], *wx_day_icon[WX_DAYS];
static lv_color16_t *wx_icon_buf[WX_DAYS], *wx_now_buf;
static Weather   wx;
static bool      wx_imperial = false;    // Charles is metric by default
static lv_obj_t *wx_unit_btn, *wx_unit_lbl;

static void wx_render(void);

static void on_wx_units(lv_event_t *e)
{
    wx_imperial = !wx_imperial;
    lv_label_set_text(wx_unit_lbl, wx_imperial ? "F" : "C");
    wx_render();                        // repaint from cache -- no refetch
}

// Oakmont, Santa Rosa
#define WX_LAT  38.4405f
#define WX_LON  -122.6190f
#define WX_ICON 72
static lv_obj_t *lbl_info, *lbl_link;

void setup()
{
    Serial.begin(115200);
    smartdisplay_init();
    smartdisplay_lcd_set_backlight(1.0f);

    if (!paint_init()) Serial.println("FATAL: paint queue would not allocate");

    lv_obj_t *scr = lv_screen_active();
    ui_shell_init(scr);
    ui_shell_set_station("SS.OAKM1.00.EHZ");

    // ---- page 1: the helicorder ----
    pg_trace = ui_shell_add_page(ICON_TRACE, "trace");
    canvas_buf = (lv_color16_t *)heap_caps_malloc(
        TRACE_W * TRACE_H * sizeof(lv_color16_t), MALLOC_CAP_SPIRAM);
    if (canvas_buf)
    {
        canvas = lv_canvas_create(pg_trace);
        lv_canvas_set_buffer(canvas, canvas_buf, TRACE_W, TRACE_H, LV_COLOR_FORMAT_RGB565);
        lv_obj_set_pos(canvas, TRACE_AX_W, 8);
        for (int32_t y = 0; y < TRACE_H; y++)
            for (int32_t x = 0; x < TRACE_W; x++)
                canvas_buf[y * TRACE_W + x] = (y == TRACE_H / 2) ? COL_AXIS : COL_BG;
        paint_register(0, canvas, canvas_buf, TRACE_W, TRACE_H);
    }
    else Serial.println("FATAL: trace canvas would not allocate");

    for (int d = 0; d < 4; d++)
        decade_px[d] = (int32_t)uv_to_px(powf(10.0f, (float)d));
    for (unsigned b = 0; b < N_AMP_BANDS; b++)
    {
        int32_t e = (int32_t)uv_to_px(AMP_BANDS[b].uv_hi);
        if (e > TRACE_H / 2) e = TRACE_H / 2;
        band_px[b] = e;
    }

    // Y axis in the left gutter. Labelled on BOTH sides of zero, because the
    // trace is bipolar and a single-sided scale would imply it is not.
    {
        static const char *anames[] = {"1", "10", "100", "1k"};
        const int32_t mid = 8 + TRACE_H / 2;
        // Start at d=1: on the log scale 1 uV sits only ~19 px from zero, so its
        // label collided with the "0". The GRIDLINE at 1 uV is still drawn -- the
        // decade is still marked, it just is not labelled twice in 37 pixels.
        for (int d = 1; d < 4; d++)
            for (int sign = -1; sign <= 1; sign += 2)
            {
                lv_obj_t *t = lv_label_create(pg_trace);
                lv_label_set_text(t, anames[d]);
                lv_obj_set_width(t, TRACE_AX_W - 10);
                lv_obj_set_style_text_align(t, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);
                lv_obj_set_style_text_color(t, lv_color_hex(0x7A8894), LV_PART_MAIN);
                lv_obj_align(t, LV_ALIGN_TOP_LEFT, 0,
                             mid - sign * decade_px[d] - 8);
            }
        lv_obj_t *z = lv_label_create(pg_trace);
        lv_label_set_text(z, "0");
        lv_obj_set_width(z, TRACE_AX_W - 10);
        lv_obj_set_style_text_align(z, LV_TEXT_ALIGN_RIGHT, LV_PART_MAIN);
        lv_obj_set_style_text_color(z, lv_color_hex(0xA8B4BE), LV_PART_MAIN);
        lv_obj_align(z, LV_ALIGN_TOP_LEFT, 0, mid - 8);

        lv_obj_t *u = lv_label_create(pg_trace);
        lv_label_set_text(u, "uV");
        lv_obj_set_style_text_color(u, lv_color_hex(0x5A6871), LV_PART_MAIN);
        lv_obj_align(u, LV_ALIGN_TOP_LEFT, 8, 8 + TRACE_H + 6);

        lv_obj_t *sc = lv_label_create(pg_trace);
        lv_label_set_text(sc, "green < 10 uV normal    yellow 10-100 something moved"
                              "    red > 100 uV unusual");
        lv_obj_set_style_text_color(sc, lv_color_hex(0x5A6871), LV_PART_MAIN);
        lv_obj_align(sc, LV_ALIGN_TOP_LEFT, TRACE_AX_W, 8 + TRACE_H + 6);
    }

    lbl_stats = lv_label_create(pg_trace);
    lv_label_set_text(lbl_stats, "connecting to pi5...");
    lv_obj_set_style_text_color(lbl_stats, lv_color_hex(0x30E060), LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_stats, &lv_font_montserrat_24, LV_PART_MAIN);
    lv_obj_align(lbl_stats, LV_ALIGN_BOTTOM_LEFT, 6, -10);

    // ---- page 2: the spectrum ----
    pg_spec = ui_shell_add_page(ICON_SPECTRUM, "spectrum");
    spec_buf = (lv_color16_t *)heap_caps_malloc(
        SPEC_W * SPEC_H * sizeof(lv_color16_t), MALLOC_CAP_SPIRAM);
    if (spec_buf)
    {
        spec_canvas = lv_canvas_create(pg_spec);
        lv_canvas_set_buffer(spec_canvas, spec_buf, SPEC_W, SPEC_H, LV_COLOR_FORMAT_RGB565);
        lv_obj_set_pos(spec_canvas, 0, 8);
        for (int32_t i = 0; i < SPEC_W * SPEC_H; i++) spec_buf[i] = COL_BG;
        paint_register(1, spec_canvas, spec_buf, SPEC_W, SPEC_H);
    }
    else Serial.println("FATAL: spectrum canvas would not allocate");

    // Frequency axis labels. Without these the panel is a pretty shape with no
    // meaning -- which is exactly how it read before.
    {
        static const float ticks[] = {0.5f, 1, 2, 5, 10, 20, 50};
        static const char *names[] = {"0.5", "1", "2", "5", "10", "20", "50"};
        for (unsigned i = 0; i < sizeof ticks / sizeof ticks[0]; i++)
        {
            lv_obj_t *t = lv_label_create(pg_spec);
            lv_label_set_text(t, names[i]);
            lv_obj_set_style_text_color(t, lv_color_hex(0x8FA0AC), LV_PART_MAIN);
            int32_t x = spec_hz_to_x(ticks[i]);
            if (x > SPEC_W - 18) x = SPEC_W - 18;
            lv_obj_align(t, LV_ALIGN_TOP_LEFT, x, SPEC_H + 12);
        }
        lv_obj_t *u = lv_label_create(pg_spec);
        lv_label_set_text(u, "Hz  (log)");
        lv_obj_set_style_text_color(u, lv_color_hex(0x5A6871), LV_PART_MAIN);
        lv_obj_align(u, LV_ALIGN_TOP_LEFT, 6, SPEC_H + 34);

        lv_obj_t *m = lv_label_create(pg_spec);
        lv_label_set_text(m, "amber ticks = known house noise: 1.05 Hz instrumental,"
                             " ~19-20 Hz HVAC high stage, ~37-41 Hz heat pump + mains alias");
        lv_obj_set_style_text_color(m, lv_color_hex(0x6C7A85), LV_PART_MAIN);
        lv_obj_align(m, LV_ALIGN_TOP_LEFT, 96, SPEC_H + 34);
    }

    // ---- page 3: information ----
    pg_info = ui_shell_add_page(ICON_INFO, "info");
    lbl_info = lv_label_create(pg_info);
    lv_label_set_text(lbl_info, "waiting for pi5...");
    lv_obj_set_style_text_color(lbl_info, lv_color_hex(0xC8D2DA), LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_info, &lv_font_montserrat_18, LV_PART_MAIN);
    lv_obj_align(lbl_info, LV_ALIGN_TOP_LEFT, 10, 10);

    // right-hand column, so the link block does not run into the detections
    lbl_link = lv_label_create(pg_info);
    lv_label_set_text(lbl_link, "");
    lv_obj_set_style_text_color(lbl_link, lv_color_hex(0xC8D2DA), LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_link, &lv_font_montserrat_18, LV_PART_MAIN);
    lv_obj_align(lbl_link, LV_ALIGN_TOP_LEFT, 380, 10);

    lv_obj_t *evh = lv_label_create(pg_info);
    lv_label_set_text(evh, "RECENT DETECTIONS");
    lv_obj_set_style_text_color(evh, lv_color_hex(0x5A6871), LV_PART_MAIN);
    lv_obj_set_style_text_font(evh, &lv_font_montserrat_18, LV_PART_MAIN);
    lv_obj_align(evh, LV_ALIGN_TOP_LEFT, 10, 290);

    for (int i = 0; i < 3; i++)
    {
        lbl_ev[i] = lv_label_create(pg_info);
        lv_label_set_text(lbl_ev[i], "");
        lv_obj_set_style_text_color(lbl_ev[i], lv_color_hex(0x8FA0AC), LV_PART_MAIN);
        lv_obj_set_style_text_font(lbl_ev[i], &lv_font_montserrat_18, LV_PART_MAIN);
        lv_obj_align(lbl_ev[i], LV_ALIGN_TOP_LEFT, 10, 320 + i * 24);
    }

    // ---- page 4: weather ----
    pg_wx = ui_shell_add_page(ICON_WEATHER, "weather");

    wx_now_buf = (lv_color16_t *)heap_caps_malloc(96 * 96 * 2, MALLOC_CAP_SPIRAM);
    if (wx_now_buf)
    {
        lv_obj_t *c = lv_canvas_create(pg_wx);
        lv_canvas_set_buffer(c, wx_now_buf, 96, 96, LV_COLOR_FORMAT_RGB565);
        lv_obj_align(c, LV_ALIGN_TOP_LEFT, 12, 14);
        icon_draw_weather(wx_now_buf, 96, 96, -1, rgb565(0xC8,0xD2,0xDA),
                          rgb565(0xFF,0xC0,0x40), COL_BG);
    }

    wx_now = lv_label_create(pg_wx);
    lv_label_set_text(wx_now, "--");
    lv_obj_set_style_text_color(wx_now, lv_color_hex(0xE8EEF2), LV_PART_MAIN);
    lv_obj_set_style_text_font(wx_now, &lv_font_montserrat_48, LV_PART_MAIN);
    lv_obj_align(wx_now, LV_ALIGN_TOP_LEFT, 122, 20);

    wx_detail = lv_label_create(pg_wx);
    lv_label_set_text(wx_detail, "fetching...");
    lv_obj_set_style_text_color(wx_detail, lv_color_hex(0x8FA0AC), LV_PART_MAIN);
    lv_obj_set_style_text_font(wx_detail, &lv_font_montserrat_18, LV_PART_MAIN);
    lv_obj_align(wx_detail, LV_ALIGN_TOP_LEFT, 122, 76);

    wx_unit_btn = lv_obj_create(pg_wx);
    lv_obj_set_size(wx_unit_btn, 62, 52);
    lv_obj_align(wx_unit_btn, LV_ALIGN_TOP_RIGHT, -12, 46);
    lv_obj_set_style_bg_color(wx_unit_btn, lv_color_hex(0x1A2027), LV_PART_MAIN);
    lv_obj_set_style_border_width(wx_unit_btn, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(wx_unit_btn, 10, LV_PART_MAIN);
    lv_obj_set_style_pad_all(wx_unit_btn, 0, LV_PART_MAIN);
    lv_obj_remove_flag(wx_unit_btn, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(wx_unit_btn, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(wx_unit_btn, on_wx_units, LV_EVENT_CLICKED, NULL);

    wx_unit_lbl = lv_label_create(wx_unit_btn);
    lv_label_set_text(wx_unit_lbl, "C");
    lv_obj_set_style_text_color(wx_unit_lbl, lv_color_hex(0xFFC040), LV_PART_MAIN);
    lv_obj_set_style_text_font(wx_unit_lbl, &lv_font_montserrat_28, LV_PART_MAIN);
    lv_obj_center(wx_unit_lbl);
    lv_obj_remove_flag(wx_unit_lbl, LV_OBJ_FLAG_CLICKABLE);

    wx_stamp = lv_label_create(pg_wx);
    lv_label_set_text(wx_stamp, "");
    lv_obj_set_style_text_color(wx_stamp, lv_color_hex(0x5A6871), LV_PART_MAIN);
    lv_obj_align(wx_stamp, LV_ALIGN_TOP_RIGHT, -12, 16);

    for (int i = 0; i < WX_DAYS; i++)
    {
        const int cw = (ui_content_w() - 24) / WX_DAYS;
        const int x  = 12 + i * cw;

        wx_day_lbl[i] = lv_label_create(pg_wx);
        lv_label_set_text(wx_day_lbl[i], "--");
        lv_obj_set_style_text_color(wx_day_lbl[i], lv_color_hex(0xC8D2DA), LV_PART_MAIN);
        lv_obj_set_style_text_font(wx_day_lbl[i], &lv_font_montserrat_24, LV_PART_MAIN);
        lv_obj_align(wx_day_lbl[i], LV_ALIGN_TOP_LEFT, x + 12, 178);

        wx_icon_buf[i] = (lv_color16_t *)heap_caps_malloc(WX_ICON * WX_ICON * 2,
                                                          MALLOC_CAP_SPIRAM);
        if (wx_icon_buf[i])
        {
            wx_day_icon[i] = lv_canvas_create(pg_wx);
            lv_canvas_set_buffer(wx_day_icon[i], wx_icon_buf[i], WX_ICON, WX_ICON,
                                 LV_COLOR_FORMAT_RGB565);
            lv_obj_align(wx_day_icon[i], LV_ALIGN_TOP_LEFT, x + 6, 212);
            icon_draw_weather(wx_icon_buf[i], WX_ICON, WX_ICON, -1,
                              rgb565(0xC8,0xD2,0xDA), rgb565(0xFF,0xC0,0x40), COL_BG);
        }

        wx_day_temp[i] = lv_label_create(pg_wx);
        lv_label_set_text(wx_day_temp[i], "");
        lv_obj_set_style_text_color(wx_day_temp[i], lv_color_hex(0x8FA0AC), LV_PART_MAIN);
        lv_obj_set_style_text_font(wx_day_temp[i], &lv_font_montserrat_18, LV_PART_MAIN);
        lv_obj_align(wx_day_temp[i], LV_ALIGN_TOP_LEFT, x + 6, 292);
    }

    ui_shell_set_help(3,
        "WEATHER\n\n"
        "Current conditions and a five-day forecast for Oakmont, from Open-Meteo, "
        "refreshed every 15 minutes. Metric throughout.\n\n"
        "It is here partly because weather genuinely shows up in the seismic "
        "record: wind loads trees and structures, pressure changes flex the "
        "ground, and the heat pump's duty cycle -- which drives the 37-41 Hz "
        "lines on the spectrum page -- follows the temperature.\n\n"
        "NO EARTHQUAKE FORECAST APPEARS HERE, and that is not an omission. "
        "Nobody can predict a specific earthquake days ahead; the USGS is "
        "explicit that they cannot and neither can anyone else. What is real is "
        "the long-run background rate, and aftershock probabilities published "
        "after a significant event. Anything more confident than that is not "
        "science.");

    ui_shell_set_help(0,
        "HELICORDER\n\n"
        "Ground motion from SS.OAKM1, one pixel column per 0.05 s, drawn as the "
        "min/max envelope of every sample in that slice -- not a decimation, so "
        "short spikes cannot be missed.\n\n"
        "The vertical scale is LOGARITHMIC and FIXED: about 39 pixels per decade "
        "of microvolts, with gridlines at 1, 10, 100 and 1000 uV. This is "
        "deliberate. An auto-scaling trace fills the screen whatever is "
        "happening, which makes a passing truck look like an earthquake. Here a "
        "quiet night is genuinely small and a felt quake is unmistakable.\n\n"
        "For scale: the noise floor is about 0.8 uV on a quiet night. The M3.3 "
        "under Larkfield-Wikiup on 2026-09-03, 13 km away and felt in the house, "
        "reached 6843 uV. Red means the trace is clipping.");
    ui_shell_set_help(1,
        "SPECTRUM\n\n"
        "A 256-point Hann-windowed FFT of the last 2.56 s, 0.39 Hz resolution, "
        "drawn on a LOGARITHMIC frequency axis from 0.5 to 50 Hz.\n\n"
        "Log, because the detection band is 1-15 Hz. On a linear axis that band "
        "gets the leftmost third of the panel while most of the width goes to "
        "20-50 Hz, which is almost entirely noise from the house.\n\n"
        "The vertical scale self-tunes to the observed range, so this shows the "
        "SHAPE of the noise, not its absolute level -- read amplitude from the "
        "helicorder instead.\n\n"
        "Amber ticks mark known house noise, so a spike there is not a mystery: "
        "1.05 Hz is an unexplained instrumental line, 19-20 Hz is the HVAC's "
        "evening high stage, and 37-41 Hz is the heat-pump compressor together "
        "with the 60 Hz mains alias at 40.0 Hz.");
    ui_shell_set_help(2,
        "INFORMATION\n\n"
        "Station identity, live signal level, link and display health, and the "
        "three most recent detections.\n\n"
        "Detections come from the STA/LTA trigger running on pi5. Each row shows "
        "the UTC start, peak amplitude, the trigger ratio (x8 means the short "
        "average was eight times the long one), duration, and the high/low "
        "frequency ratio -- a rough discriminator, since local earthquakes carry "
        "more high frequency than a door slam.\n\n"
        "A detection is NOT a confirmed earthquake. Most are cultural noise.\n\n"
        "The clock is UTC, taken from pi5 on each fetch; there is no clock in "
        "this display.");

    ui_shell_select(0);

    Serial.printf("\n=== live helicorder: %s:%d ===\n", SEISMO_HOST, SEISMO_PORT);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

// Render the weather page from the cached fetch. Separate from fetching so the
// units toggle repaints instantly instead of hitting the network.
static void wx_render(void)
{
    if (!wx.valid) return;
    const bool F = wx_imperial;
    auto T = [&](float c) { return F ? c * 9.0f / 5.0f + 32.0f : c; };
    const char *TU = F ? "F" : "C";

    char b[128];
    snprintf(b, sizeof b, "%.0f %s", T(wx.temp_c), TU);
    lv_label_set_text(wx_now, b);

    snprintf(b, sizeof b, "%s\nfeels %.0f %s   %d%% RH\nwind %.0f %s   %.0f hPa",
             wx_text(wx.code), T(wx.apparent_c), TU, wx.humidity_pct,
             F ? wx.wind_kmh * 0.621371f : wx.wind_kmh, F ? "mph" : "km/h",
             wx.pressure_hpa);
    lv_label_set_text(wx_detail, b);

    if (wx_now_buf)
    {
        icon_draw_weather(wx_now_buf, 96, 96, wx.code,
                          rgb565(0xC8,0xD2,0xDA), rgb565(0xFF,0xC0,0x40), COL_BG);
        lv_obj_invalidate(lv_obj_get_child(pg_wx, 0));
    }
    for (int i = 0; i < WX_DAYS; i++)
    {
        lv_label_set_text(wx_day_lbl[i], wx.day[i].label);
        snprintf(b, sizeof b, "%.0f / %.0f %s\n%d%% rain",
                 T(wx.day[i].tmax), T(wx.day[i].tmin), TU, wx.day[i].precip_pct);
        lv_label_set_text(wx_day_temp[i], b);
        if (wx_icon_buf[i])
        {
            icon_draw_weather(wx_icon_buf[i], WX_ICON, WX_ICON, wx.day[i].code,
                              rgb565(0xC8,0xD2,0xDA), rgb565(0xFF,0xC0,0x40), COL_BG);
            lv_obj_invalidate(wx_day_icon[i]);
        }
    }
    const double u = utc_now();
    if (u > 0)
    {
        const time_t tt = (time_t)u;
        struct tm g; gmtime_r(&tt, &g);
        snprintf(b, sizeof b, "updated %02d:%02d UTC", g.tm_hour, g.tm_min);
        lv_label_set_text(wx_stamp, b);
    }
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
            // peak_uv_boot is still tracked; it is reported on the info page
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
            ui_shell_set_wifi((int)WiFi.RSSI(), true);
            if (!last_up) log_i("wifi up: %s  %d dBm", ip.c_str(), WiFi.RSSI());
        }
        else
        {
            ui_shell_set_wifi(0, false);
        }
        last_up = up; ticks++;

        const double u = utc_now();
        if (u > 0)
        {
            char ib[320];
            snprintf(ib, sizeof ib,
                     "STATION\n"
                     "  SS.OAKM1.00.EHZ\n"
                     "  100 sps   PGA 64\n"
                     "  Oakmont, Sonoma County\n"
                     "  4.5 Hz vertical geophone\n"
                     "  garage slab\n\n"
                     "LIVE\n"
                     "  rms %.1f uV\n"
                     "  feed age %.1f s\n"
                     "  peak since boot %.0f uV",
                     last_rms, last_age, peak_uv_boot);
            lv_label_set_text(lbl_info, ib);

            char lb[300];
            const uint32_t up = millis() / 1000;
            snprintf(lb, sizeof lb,
                     "LINK\n"
                     "  %s\n"
                     "  %d dBm\n\n"
                     "DISPLAY\n"
                     "  up %luh %02lum\n"
                     "  heap %u free\n"
                     "  paint queue %u",
                     WiFi.localIP().toString().c_str(), (int)WiFi.RSSI(),
                     (unsigned long)(up / 3600), (unsigned long)((up / 60) % 60),
                     (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                     (unsigned)paint_pending());
            lv_label_set_text(lbl_link, lb);
        }
    }

    // The clock follows the TIME, not a timer. Updating it from the same 1 s
    // tick as everything else let the tick drift against the real second
    // boundary, so occasionally two updates landed inside one second and a
    // second appeared to be skipped. Check often, act only when the value
    // actually changes -- ui_shell_set_clock() repaints only altered digits, so
    // polling at 10 Hz costs nothing.
    {
        static uint32_t last_clk = 0;
        static int      last_sec = -1;
        if (now - last_clk >= 100)
        {
            last_clk = now;
            const double u = utc_now();
            if (u > 0)
            {
                const time_t tt = (time_t)u;
                if ((int)tt != last_sec)
                {
                    last_sec = (int)tt;
                    struct tm g;
                    gmtime_r(&tt, &g);
                    char cbuf[16];
                    snprintf(cbuf, sizeof cbuf, "%02d:%02d:%02d",
                             g.tm_hour, g.tm_min, g.tm_sec);
                    ui_shell_set_clock(cbuf);
                }
            }
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
            // peak_uv_boot is still tracked; it is reported on the info page
        }
    }

    // Paced drain: real-time rate, servo-corrected toward the target depth.
    {
        static uint32_t last_drain = 0;
        static float    credit = 0.0f;
        if (last_drain == 0) last_drain = now;
        const float dt = (now - last_drain) / 1000.0f;
        last_drain = now;

        const size_t depth = (colq_head + COLQ_N - colq_tail) % COLQ_N;
        float rate = dt / COL_PERIOD_S;                       // columns of real time
        rate *= 1.0f + COLQ_SERVO * ((float)depth - COLQ_TARGET) / COLQ_TARGET;
        if (rate < 0.0f) rate = 0.0f;
        const float cap = 4.0f * dt / COL_PERIOD_S;           // never sprint
        if (rate > cap) rate = cap;

        credit += rate;
        int n = (int)credit;
        credit -= n;
        if (n > 24) n = 24;                                   // hard safety stop
        for (int k = 0; k < n && colq_tail != colq_head; k++)
        {
            draw_column(col, colq[colq_tail].mn, colq[colq_tail].mx);
            col = (col + 1) % TRACE_W;
            colq_tail = (colq_tail + 1) % COLQ_N;
        }
        colq_depth = depth;
    }

    // NO periodic esp_lcd_rgb_panel_restart() here. Restarting DMA disrupts a
    // frame, so calling it on a timer injects a glitch every interval by design.
    // CONFIG_LCD_RGB_RESTART_IN_VSYNC (=1 in this framework) already restarts
    // automatically, and only when the hardware has actually desynced.
    // display_restart_panel() remains available as a manual lever.


    // Weather: every 15 minutes. Open-Meteo updates hourly, so anything faster
    // is pure waste of their bandwidth and ours.
    {
        static uint32_t last_wx = 0;
        if (WiFi.status() == WL_CONNECTED &&
            (last_wx == 0 || now - last_wx >= 900000UL))
        {
            last_wx = now;
            if (weather_fetch(&wx, WX_LAT, WX_LON)) wx_render();
        }
    }

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
