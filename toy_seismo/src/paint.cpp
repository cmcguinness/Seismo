#include "paint.h"
#include <string.h>

struct Cmd { uint8_t target; int16_t x, y, w, h; lv_color16_t c; };

static Cmd      q[PAINT_QUEUE_N];
static uint16_t q_head = 0, q_tail = 0;
static uint32_t q_dropped = 0;

struct Target {
    lv_obj_t     *canvas;
    lv_color16_t *buf;
    int16_t       w, h;
    // dirty bounding box accumulated during a drain, flushed as ONE invalidate
    int16_t       dx0, dy0, dx1, dy1;
    bool          dirty;
};
static Target tg[PAINT_TARGETS];

void paint_register(uint8_t target, lv_obj_t *canvas, lv_color16_t *buf,
                    int16_t w, int16_t h)
{
    if (target >= PAINT_TARGETS) return;
    tg[target].canvas = canvas;
    tg[target].buf    = buf;
    tg[target].w      = w;
    tg[target].h      = h;
    tg[target].dirty  = false;
}

void paint_rect(uint8_t target, int16_t x, int16_t y, int16_t w, int16_t h,
                lv_color16_t c)
{
    if (target >= PAINT_TARGETS || w <= 0 || h <= 0) return;

    const uint16_t nxt = (uint16_t)((q_head + 1) % PAINT_QUEUE_N);
    if (nxt == q_tail)
    {
        // Full. Drop the OLDEST: on a scrolling display the freshest pixels are
        // the ones worth keeping, and dropping newest would freeze the trace.
        q_tail = (uint16_t)((q_tail + 1) % PAINT_QUEUE_N);
        q_dropped++;
    }
    q[q_head] = (Cmd){target, x, y, w, h, c};
    q_head = nxt;
}

size_t paint_pending(void)
{
    return (size_t)((q_head + PAINT_QUEUE_N - q_tail) % PAINT_QUEUE_N);
}

static inline void mark_dirty(Target &t, int16_t x0, int16_t y0, int16_t x1, int16_t y1)
{
    if (!t.dirty) { t.dx0 = x0; t.dy0 = y0; t.dx1 = x1; t.dy1 = y1; t.dirty = true; return; }
    if (x0 < t.dx0) t.dx0 = x0;
    if (y0 < t.dy0) t.dy0 = y0;
    if (x1 > t.dx1) t.dx1 = x1;
    if (y1 > t.dy1) t.dy1 = y1;
}

size_t paint_drain(uint32_t budget_px)
{
    uint32_t spent = 0;

    while (q_tail != q_head && spent < budget_px)
    {
        const Cmd cmd = q[q_tail];
        Target &t = tg[cmd.target];
        if (!t.buf) { q_tail = (uint16_t)((q_tail + 1) % PAINT_QUEUE_N); continue; }

        int16_t x0 = cmd.x, y0 = cmd.y;
        int16_t x1 = (int16_t)(cmd.x + cmd.w - 1), y1 = (int16_t)(cmd.y + cmd.h - 1);
        if (x0 < 0) x0 = 0;
        if (y0 < 0) y0 = 0;
        if (x1 >= t.w) x1 = (int16_t)(t.w - 1);
        if (y1 >= t.h) y1 = (int16_t)(t.h - 1);
        if (x1 < x0 || y1 < y0) { q_tail = (uint16_t)((q_tail + 1) % PAINT_QUEUE_N); continue; }

        for (int16_t yy = y0; yy <= y1; yy++)
        {
            lv_color16_t *row = t.buf + (int32_t)yy * t.w + x0;
            for (int16_t xx = 0; xx <= x1 - x0; xx++) row[xx] = cmd.c;
        }
        spent += (uint32_t)(x1 - x0 + 1) * (uint32_t)(y1 - y0 + 1);
        mark_dirty(t, x0, y0, x1, y1);

        q_tail = (uint16_t)((q_tail + 1) % PAINT_QUEUE_N);
    }

    // ONE invalidate per target per drain. LVGL then re-renders that bbox in
    // DRAW_LINES strips, each sized to stay inside the latency budget, so the
    // panel never sees a single long bus hold.
    //
    // ⚠️ lv_obj_invalidate_area() takes ABSOLUTE SCREEN coordinates, not
    // canvas-local ones. Passing local coords silently invalidates the wrong
    // region -- and silently is the problem: a canvas at y=284 had its local
    // rows 0..103 mapped to absolute rows 0..103, which do not intersect it at
    // all, so it never repainted and rendered permanently blank while every
    // pixel was being written correctly. A canvas near the top of the screen
    // partially overlaps and appears to "work", which hides the bug.
    for (int i = 0; i < PAINT_TARGETS; i++)
    {
        if (!tg[i].dirty || !tg[i].canvas) continue;
        lv_area_t obj;
        lv_obj_get_coords(tg[i].canvas, &obj);
        lv_area_t a = {(int32_t)(obj.x1 + tg[i].dx0), (int32_t)(obj.y1 + tg[i].dy0),
                       (int32_t)(obj.x1 + tg[i].dx1), (int32_t)(obj.y1 + tg[i].dy1)};
        lv_obj_invalidate_area(tg[i].canvas, &a);
        tg[i].dirty = false;
    }
    return paint_pending();
}
