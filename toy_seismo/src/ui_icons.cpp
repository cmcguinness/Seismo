#include "ui_icons.h"
#include <math.h>

static inline void px(lv_color16_t *b, int16_t w, int16_t h, int x, int y, lv_color16_t c)
{
    if (x >= 0 && y >= 0 && x < w && y < h) b[(int32_t)y * w + x] = c;
}

static void fill(lv_color16_t *b, int16_t w, int16_t h, lv_color16_t c)
{
    for (int32_t i = 0; i < (int32_t)w * h; i++) b[i] = c;
}

static void vbar(lv_color16_t *b, int16_t w, int16_t h, int x, int y0, int y1,
                 int thick, lv_color16_t c)
{
    for (int t = 0; t < thick; t++)
        for (int y = y0; y <= y1; y++) px(b, w, h, x + t, y, c);
}

void icon_draw(lv_color16_t *buf, int16_t w, int16_t h,
               icon_kind_t kind, lv_color16_t fg, lv_color16_t bg)
{
    fill(buf, w, h, bg);
    const int m = w / 8;                 // margin
    const int iw = w - 2 * m, ih = h - 2 * m;

    switch (kind)
    {
    case ICON_TRACE:
    {
        // A seismogram: quiet, burst, quiet -- reads as "waveform" at 48 px.
        const int mid = h / 2;
        for (int i = 0; i < iw; i++)
        {
            const float t = (float)i / iw;
            const float env = expf(-powf((t - 0.5f) * 4.2f, 2.0f));
            const float a = sinf(t * 38.0f) * (0.12f + 0.88f * env);
            const int amp = (int)(a * (ih / 2 - 1));
            const int y0 = mid - (amp > 0 ? amp : -amp);
            const int y1 = mid + (amp > 0 ? amp : -amp);
            for (int y = y0; y <= y1; y++) px(buf, w, h, m + i, y, fg);
        }
        break;
    }
    case ICON_SPECTRUM:
    {
        const int n = 5, gap = 2;
        const int bw = (iw - gap * (n - 1)) / n;
        const int hgt[5] = {40, 75, 55, 100, 30};      // percent
        for (int i = 0; i < n; i++)
        {
            const int bh = ih * hgt[i] / 100;
            vbar(buf, w, h, m + i * (bw + gap), h - m - bh, h - m - 1, bw, fg);
        }
        break;
    }
    case ICON_INFO:
    {
        const int cx = w / 2, cy = h / 2, r = (w < h ? w : h) / 2 - m / 2;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                const float d = sqrtf((float)((x - cx) * (x - cx) + (y - cy) * (y - cy)));
                if (d <= r && d >= r - 2.5f) px(buf, w, h, x, y, fg);
            }
        vbar(buf, w, h, cx - 1, cy - r / 3, cy + r / 2, 3, fg);      // stem
        vbar(buf, w, h, cx - 1, cy - r / 2 - 4, cy - r / 2 - 1, 3, fg); // dot
        break;
    }
    case ICON_EVENTS:
        for (int i = 0; i < 4; i++)
        {
            const int y = m + i * (ih / 4);
            for (int x = m; x < m + 4; x++) px(buf, w, h, x, y, fg);
            for (int x = m + 7; x < w - m; x++) px(buf, w, h, x, y, fg);
        }
        break;
    case ICON_WEATHER:
    {
        const int cx = w * 0.62f, cy = h * 0.38f, r = w / 5;
        for (int y = 0; y < h; y++)                        // sun
            for (int x = 0; x < w; x++)
            {
                const float d = sqrtf((float)((x-cx)*(x-cx) + (y-cy)*(y-cy)));
                if (d <= r) px(buf, w, h, x, y, fg);
            }
        const int bx = w * 0.42f, by = h * 0.62f, br = w / 4;   // cloud
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                const float d1 = sqrtf((float)((x-bx)*(x-bx) + (y-by)*(y-by)));
                const float d2 = sqrtf((float)((x-bx-br)*(x-bx-br) + (y-by+3)*(y-by+3)));
                if (d1 <= br || d2 <= br * 0.8f) px(buf, w, h, x, y, fg);
            }
        for (int x = bx - br; x <= bx + br + 4; x++)
            for (int y = by; y <= by + br; y++) px(buf, w, h, x, y, fg);
        break;
    }
    case ICON_SETTINGS:
    default:
    {
        const int cx = w / 2, cy = h / 2, r = (w < h ? w : h) / 2 - m;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                const float dx = x - cx, dy = y - cy;
                const float d = sqrtf(dx * dx + dy * dy);
                const float a = atan2f(dy, dx);
                const float lobe = r * (0.72f + 0.28f * (cosf(a * 8.0f) > 0 ? 1.f : 0.f));
                if (d <= lobe && d >= r * 0.34f) px(buf, w, h, x, y, fg);
            }
        break;
    }
    }
}

void icon_draw_wifi(lv_color16_t *buf, int16_t w, int16_t h, int level,
                    lv_color16_t on, lv_color16_t off, lv_color16_t bg)
{
    fill(buf, w, h, bg);
    const float cx = (w - 1) / 2.0f, cy = (float)(h - 2);

    // three nested arcs plus the dot, like a phone's signal glyph
    const float r_out[3] = {h * 0.92f, h * 0.62f, h * 0.34f};
    const float band = h * 0.13f;

    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++)
        {
            const float dx = x - cx, dy = cy - y;
            if (dy < 0) continue;
            if (dy < fabsf(dx) * 0.62f) continue;      // ~58 deg half-angle wedge
            const float d = sqrtf(dx * dx + dy * dy);
            for (int a = 0; a < 3; a++)
                if (d <= r_out[a] && d >= r_out[a] - band)
                {
                    // arc 0 is the outermost = strongest signal
                    const int need = 3 - a;            // 3,2,1
                    px(buf, w, h, x, y, (level >= need) ? on : off);
                }
        }
    // the dot at the origin is always lit if associated at all
    for (int y = -2; y <= 1; y++)
        for (int x = -2; x <= 1; x++)
            px(buf, w, h, (int)cx + x, (int)cy + y, level >= 0 ? on : off);
}

// WMO code groups: 0 clear, 1-3 partly/overcast, 45/48 fog, 51-67 drizzle/rain,
// 71-77 snow, 80-82 showers, 95-99 thunderstorm.
void icon_draw_weather(lv_color16_t *buf, int16_t w, int16_t h, int c,
                       lv_color16_t fg, lv_color16_t accent, lv_color16_t bg)
{
    fill(buf, w, h, bg);
    const bool clear  = (c == 0);
    const bool partly = (c >= 1 && c <= 2);
    const bool fog    = (c == 45 || c == 48);
    const bool snow   = (c >= 71 && c <= 77) || c == 85 || c == 86;
    const bool storm  = (c >= 95);
    const bool wet    = (c >= 51 && c <= 67) || (c >= 80 && c <= 82) || storm;

    const int cx = clear ? w / 2 : (int)(w * 0.64f);
    const int cy = clear ? h / 2 : (int)(h * 0.34f);
    const int r  = clear ? w / 4 : w / 6;

    if (clear || partly)                                  // sun disc + rays
    {
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                if (sqrtf((float)((x-cx)*(x-cx)+(y-cy)*(y-cy))) <= r)
                    px(buf, w, h, x, y, accent);
        if (clear)
            for (int a = 0; a < 360; a += 45)
            {
                const float rad = a * 3.14159265f / 180.0f;
                for (int t = r + 3; t < r + 9; t++)
                    px(buf, w, h, cx + (int)(t*cosf(rad)), cy + (int)(t*sinf(rad)), accent);
            }
    }

    if (!clear)                                           // cloud body
    {
        const int bx = (int)(w * 0.42f), by = (int)(h * 0.55f), br = w / 4;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                const float d1 = sqrtf((float)((x-bx)*(x-bx)+(y-by)*(y-by)));
                const float d2 = sqrtf((float)((x-bx-br)*(x-bx-br)+(y-by+4)*(y-by+4)));
                if (d1 <= br || d2 <= br * 0.85f) px(buf, w, h, x, y, fg);
            }
        for (int x = bx - br; x <= bx + br + 5; x++)
            for (int y = by; y <= by + br - 2; y++) px(buf, w, h, x, y, fg);
    }

    if (fog)
        for (int i = 0; i < 3; i++)
            for (int x = w / 6; x < w - w / 6; x++)
                px(buf, w, h, x, (int)(h * 0.72f) + i * 6, fg);

    if (wet)                                              // rain streaks
        for (int i = 0; i < 4; i++)
        {
            const int x0 = w / 5 + i * (w / 6);
            for (int k = 0; k < 8; k++)
                px(buf, w, h, x0 - k / 2, (int)(h * 0.76f) + k, accent);
        }
    if (snow)
        for (int i = 0; i < 4; i++)
        {
            const int x0 = w / 5 + i * (w / 6), y0 = (int)(h * 0.82f);
            for (int k = -3; k <= 3; k++)
            {
                px(buf, w, h, x0 + k, y0, fg);
                px(buf, w, h, x0, y0 + k, fg);
            }
        }
    if (storm)
        for (int k = 0; k < 14; k++)
            px(buf, w, h, w / 2 + (k < 7 ? 4 - k : k - 10), (int)(h * 0.74f) + k, accent);
}
