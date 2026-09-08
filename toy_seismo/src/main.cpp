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
#include <esp32_smartdisplay.h>
#include "wifi_secrets.h"

// ---------------------------------------------------------------- geometry --
#define TRACE_X       0
#define TRACE_Y       64
#define TRACE_W       800
#define TRACE_H       360
// Seconds of ground motion per pixel column. This is the ONE number that decides
// whether the display reads as live or as a chart recorder:
//   0.05  -> 20 px/s, 40 s across the screen   (live scroller -- what a demo wants)
//   1.0   ->  1 px/s, 13.3 min across          (wall helicorder -- looks frozen)
// /v1/live carries 30 s of history, so at 0.05 the first poll fills 600 of the
// 800 columns immediately instead of drawing a 30 px stub.
#define COL_PERIOD_S  0.05

static lv_obj_t *canvas, *lbl_title, *lbl_stats, *lbl_net;
static lv_color16_t *canvas_buf;

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

// Draw one column. min/max are µV; the column is the helicorder envelope for
// that second, which is the only honest reduction when 100 samples share one
// pixel -- a decimation would alias away exactly the spikes we care about.
static void draw_column(int32_t x, float vmin, float vmax)
{
    const int32_t mid = TRACE_H / 2;

    // Auto-scale to a slow envelope average, not the peak: a quiet desk still
    // shows life, and one slammed door does not flatten the next ten minutes.
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

    const lv_color16_t wave = clipped ? COL_HOT : COL_WAVE;

    for (int32_t y = 0; y < TRACE_H; y++)
    {
        lv_color16_t c = COL_BG;
        if (y == mid) c = COL_GRID;                 // centre line
        if (y >= y0 && y <= y1) c = wave;
        canvas_buf[y * TRACE_W + x] = c;
    }

    // erase a gap ahead of the cursor so the write head is visible
    for (int32_t d = 1; d <= 3; d++)
    {
        const int32_t xc = (x + d) % TRACE_W;
        for (int32_t y = 0; y < TRACE_H; y++)
            canvas_buf[y * TRACE_W + xc] = (y == mid) ? COL_GRID : COL_BG;
    }

    lv_area_t dirty = {x, 0, x + 3, TRACE_H - 1};
    if (dirty.x2 >= TRACE_W) dirty.x2 = TRACE_W - 1;
    lv_obj_invalidate_area(canvas, &dirty);
}

// Feed one sample, at absolute time t, into the current column bin.
static void feed(double t, float uv)
{
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

    draw_column(col, col_min, col_max);
    col = (col + 1) % TRACE_W;

    // A gap (missed polls) must advance the cursor, not compress time.
    for (int64_t s = col_epoch + 1; s < sec && s < col_epoch + TRACE_W; s++)
    {
        draw_column(col, 0.0f, 0.0f);
        col = (col + 1) % TRACE_W;
    }
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

    lv_label_set_text_fmt(lbl_stats, "rms %.1f uV   age %.1fs   +%u", rms, age, (unsigned)used);
    log_i("live: n=%u used=%u col=%d t_end=%.1f", (unsigned)n, (unsigned)used, (int)col, t_end);
    return used > 0;    // "productive?", so the caller can pace itself
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

    lbl_title = lv_label_create(scr);
    lv_label_set_text(lbl_title, "SS.OAKM1.00.EHZ   Oakmont, Sonoma County");
    lv_obj_set_style_text_color(lbl_title, lv_color_hex(0xE8EEF2), LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_title, &lv_font_montserrat_24, LV_PART_MAIN);
    lv_obj_align(lbl_title, LV_ALIGN_TOP_LEFT, 12, 10);

    lbl_net = lv_label_create(scr);
    lv_label_set_text(lbl_net, "wifi...");
    lv_obj_set_style_text_color(lbl_net, lv_color_hex(0x88939B), LV_PART_MAIN);
    lv_obj_align(lbl_net, LV_ALIGN_TOP_RIGHT, -12, 14);

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
    }
    else
        Serial.println("FATAL: trace canvas would not allocate in PSRAM");

    lbl_stats = lv_label_create(scr);
    lv_label_set_text(lbl_stats, "waiting for pi5...");
    lv_obj_set_style_text_color(lbl_stats, lv_color_hex(0x30E060), LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_stats, &lv_font_montserrat_24, LV_PART_MAIN);
    lv_obj_align(lbl_stats, LV_ALIGN_BOTTOM_LEFT, 12, -12);

    Serial.printf("\n=== live helicorder: %s:%d ===\n", SEISMO_HOST, SEISMO_PORT);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);            // latency matters more than the milliamps
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void loop()
{
    static uint32_t last = millis(), last_poll = 0, last_net = 0;
    const uint32_t now = millis();
    lv_tick_inc(now - last);
    last = now;

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
        if (up)
            lv_label_set_text_fmt(lbl_net, "%s  %d dBm", WiFi.localIP().toString().c_str(), WiFi.RSSI());
        else
            lv_label_set_text(lbl_net, "wifi: connecting");
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
    }

    lv_timer_handler();
    delay(5);
}
