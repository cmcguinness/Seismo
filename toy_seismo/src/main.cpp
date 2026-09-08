// Bring-up smoke test for the Sunton/DIYmalls ESP32-8048S050C-I.
//
// This is deliberately a diagnostic, not a hello-world. It answers the four
// things that are actually in doubt on a first flash of an RGB565 panel:
//
//   1. does the panel light and is the resolution what we think (800x480)
//   2. is the colour order right -- R and B swapped is THE classic RGB565
//      wiring/config bug, and a red bar that renders blue says so instantly
//   3. is the octal PSRAM present (768 KB of framebuffer depends on it)
//   4. does GT911 touch report coordinates, un-mirrored, in the right axes
//
// Touch anywhere: the readout follows your finger. Top-left should read a
// small x AND a small y. If either axis counts backwards, the panel config
// needs mirroring -- better to learn that here than inside a UI.

#include <Arduino.h>
#include <esp32_smartdisplay.h>

static lv_obj_t *readout;
static lv_obj_t *canvas;
static lv_color16_t *canvas_buf;

#define TRACE_W 800
#define TRACE_H 280

static void touch_cb(lv_event_t *e)
{
    lv_indev_t *indev = lv_indev_active();
    if (!indev)
        return;

    static uint32_t last_lbl = 0;
    const uint32_t now = millis();
    if (now - last_lbl < 50)  // 20 Hz is plenty for a coordinate readout
        return;
    last_lbl = now;

    lv_point_t p;
    lv_indev_get_point(indev, &p);
    // fixed width, so the redrawn area does not change size with the digits
    static int32_t px = -1, py = -1;
    if (p.x == px && p.y == py)
        return;                      // nothing changed: do not repaint text
    px = p.x; py = p.y;
    lv_label_set_text_fmt(readout, "touch  x=%3d  y=%3d", (int)p.x, (int)p.y);
}

void setup()
{
    Serial.begin(115200);
    smartdisplay_init();
    smartdisplay_lcd_set_backlight(1.0f);

    lv_display_t *disp = lv_display_get_default();
    const int32_t w = lv_display_get_horizontal_resolution(disp);
    const int32_t h = lv_display_get_vertical_resolution(disp);

    // --- serial report, so the numbers survive even if the panel is dark ---
    Serial.printf("\n=== %s bring-up ===\n", BOARD_NAME);
    Serial.printf("resolution : %ld x %ld\n", (long)w, (long)h);
    Serial.printf("PSRAM      : %u bytes total, %u free\n",
                  (unsigned)ESP.getPsramSize(), (unsigned)ESP.getFreePsram());
    Serial.printf("heap       : %u free\n", (unsigned)ESP.getFreeHeap());
    Serial.printf("flash      : %u bytes\n", (unsigned)ESP.getFlashChipSize());
    if (ESP.getPsramSize() == 0)
        Serial.println("WARNING: no PSRAM detected -- the framebuffer needs 768 KB");

    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_black(), LV_PART_MAIN);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    // --- scrolling trace: the REAL workload, not a stress test ---
    // A helicorder does not shift the framebuffer (a 448 KB memmove per frame).
    // It parks a wrapping cursor and draws ONE column per tick, erasing the
    // column ahead of it -- O(1) work per frame, which is what the wall display
    // will actually do. If the panel tears under this, the tearing is real; if
    // it only tore under the old label-rewrite test, that was my artifact.
    canvas_buf = (lv_color16_t *)heap_caps_malloc(
        TRACE_W * TRACE_H * sizeof(lv_color16_t), MALLOC_CAP_SPIRAM);
    if (canvas_buf)
    {
        canvas = lv_canvas_create(scr);
        lv_canvas_set_buffer(canvas, canvas_buf, TRACE_W, TRACE_H, LV_COLOR_FORMAT_RGB565);
        lv_obj_align(canvas, LV_ALIGN_TOP_MID, 0, 0);
        lv_canvas_fill_bg(canvas, lv_color_black(), LV_OPA_COVER);
    }
    else
        Serial.println("WARNING: could not allocate trace canvas in PSRAM");

    // --- the numbers, on screen too ---
    lv_obj_t *info = lv_label_create(scr);
    lv_label_set_text_fmt(info,
                          "%s\n%ld x %ld    PSRAM %u MB    flash %u MB",
                          BOARD_NAME, (long)w, (long)h,
                          (unsigned)(ESP.getPsramSize() >> 20),
                          (unsigned)(ESP.getFlashChipSize() >> 20));
    lv_obj_set_style_text_color(info, lv_color_white(), LV_PART_MAIN);
    lv_obj_set_style_text_font(info, &lv_font_montserrat_24, LV_PART_MAIN);
    lv_obj_align(info, LV_ALIGN_CENTER, 0, 20);

    readout = lv_label_create(scr);
    lv_label_set_text(readout, "touch the screen");
    lv_obj_set_style_text_color(readout, lv_color_hex(0xFFD000), LV_PART_MAIN);
    lv_obj_set_style_text_font(readout, &lv_font_montserrat_28, LV_PART_MAIN);
    lv_obj_align(readout, LV_ALIGN_BOTTOM_MID, 0, -30);

    lv_obj_add_flag(scr, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(scr, touch_cb, LV_EVENT_PRESSING, NULL);
    lv_obj_add_event_cb(scr, touch_cb, LV_EVENT_PRESSED, NULL);
}

static inline lv_color16_t rgb565(uint8_t r, uint8_t g, uint8_t b)
{
    lv_color16_t c;
    c.red = r >> 3; c.green = g >> 2; c.blue = b >> 3;
    return c;
}

static void trace_step()
{
    if (!canvas)
        return;

    // Throttle to a realistic drawing rate. A helicorder scrolling a 30-minute
    // line across 800 px advances 0.44 px/s; even a fast live scroller is ~30
    // columns/s. Free-running at 174 fps -- ~400x the real rate -- was a
    // benchmark artifact, not the workload, and it is what produced the
    // residual desync spikes.
    static uint32_t last_col = 0;
    if (millis() - last_col < 33)   // 30 columns/s, still ~70x reality
        return;
    last_col = millis();

    static int32_t x = 0;
    static float phase = 0.0f;

    phase += 0.08f;
    const float env = 0.25f + 0.75f * fabsf(sinf(phase * 0.03f));
    int32_t half = (int32_t)(env * (TRACE_H / 2 - 4) * sinf(phase));
    if (half < 0) half = -half;
    const int32_t mid = TRACE_H / 2;

    // Write straight into the RGB565 buffer. The LVGL draw-layer API was costing
    // 75 ms/frame because lv_canvas_finish_layer() invalidates the WHOLE canvas
    // (448 KB) regardless of how few pixels changed. A helicorder touches one
    // column, so touch one column.
    const lv_color16_t bg = rgb565(0, 0, 0);
    const lv_color16_t fg = rgb565(0x30, 0xE0, 0x60);

    for (int32_t dx = 1; dx <= 3; dx++)          // erase ahead of the cursor
    {
        const int32_t xc = (x + dx) % TRACE_W;
        for (int32_t y = 0; y < TRACE_H; y++)
            canvas_buf[y * TRACE_W + xc] = bg;
    }
    for (int32_t y = 0; y < TRACE_H; y++)        // draw this column
        canvas_buf[y * TRACE_W + x] = (y >= mid - half && y <= mid + half) ? fg : bg;

    lv_area_t dirty = {x, 0, (x + 3) % TRACE_W, TRACE_H - 1};
    if (dirty.x2 < dirty.x1) dirty.x2 = TRACE_W - 1;   // do not wrap an area
    lv_obj_invalidate_area(canvas, &dirty);

    x = (x + 1) % TRACE_W;
}

void loop()
{
    static uint32_t last = millis();
    const uint32_t now = millis();
    lv_tick_inc(now - last);
    last = now;

    const uint32_t ta = micros();
    trace_step();          // one column per pass -- the real workload
    const uint32_t dt_trace = micros() - ta;

    const uint32_t t0 = micros();
    lv_timer_handler();
    const uint32_t dt = micros() - t0;

    // report the render cost: mean and worst-case over a 2 s window
    static uint32_t acc = 0, worst = 0, n = 0, last_report = 0, acc_tr = 0;
    acc += dt; acc_tr += dt_trace; n++;
    if (dt > worst) worst = dt;
    if (now - last_report >= 2000)
    {
        Serial.printf("trace_step %lu us | lv_timer_handler mean %lu us worst %lu us | %lu fps\n",
                      (unsigned long)(acc_tr / (n ? n : 1)),
                      (unsigned long)(acc / (n ? n : 1)),
                      (unsigned long)worst,
                      (unsigned long)(n / 2));
        acc = worst = n = acc_tr = 0;
        last_report = now;
    }

    delay(5);
}
