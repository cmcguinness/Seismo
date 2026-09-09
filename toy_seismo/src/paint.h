// Write-at-will paint queue.
//
// THE PROBLEM THIS SOLVES. The panel scans an 800x480x2 framebuffer out of
// PSRAM continuously. Measured on this board the bus gives ~40 MB/s total, and
// a single operation that holds it for more than ~1 ms starves the LCD FIFO and
// desyncs the scanout into a permanently shifted image. So *when* and *how much*
// you draw matters more than what you draw -- and that is a terrible constraint
// to spread across application code.
//
// THE CONTRACT. Application code enqueues primitives whenever it likes and never
// blocks. paint_drain() executes them inside the vertical blanking interval,
// where the RGB peripheral fetches nothing and the bus is free, up to a pixel
// budget per frame. Work spills to the next frame or the one after; nothing is
// lost, nothing bursts. Drawing is decoupled from refresh.
//
// Text and widgets stay with LVGL -- they redraw rarely and are not the problem.
// This queue owns the high-rate pixel traffic: the helicorder and the spectrum.
#pragma once
#include <lvgl.h>
#include <stdint.h>
#include <stddef.h>

#define PAINT_TARGETS   2      // 0 = trace canvas, 1 = spectrum canvas
#define PAINT_QUEUE_N   1024   // commands; ~10 KB. Overflow drops OLDEST.

// Register a canvas as a paint target. buf must be LV_COLOR_FORMAT_RGB565.
void paint_register(uint8_t target, lv_obj_t *canvas, lv_color16_t *buf,
                    int16_t w, int16_t h);

// --- enqueue: cheap, non-blocking, safe to call as often as you like ---
void paint_rect(uint8_t target, int16_t x, int16_t y, int16_t w, int16_t h,
                lv_color16_t c);
static inline void paint_vline(uint8_t target, int16_t x, int16_t y0, int16_t y1,
                               lv_color16_t c)
{
    if (y1 < y0) { const int16_t t = y0; y0 = y1; y1 = t; }
    paint_rect(target, x, y0, 1, (int16_t)(y1 - y0 + 1), c);
}

// Execute queued work, up to budget_px pixels. Call once per frame from inside
// the blanking window. Returns the number of commands still pending.
size_t paint_drain(uint32_t budget_px);

size_t paint_pending(void);
