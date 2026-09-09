// Programmatically drawn square icons for the nav rail, plus a Wi-Fi strength
// meter for the title bar. Drawn as pixels into RGB565 buffers rather than
// using a symbol font: these are shapes, not glyphs, and this keeps the library
// free of font dependencies and lets an icon be redrawn in a new colour when it
// becomes the active page.
#pragma once
#include <lvgl.h>
#include <stdint.h>

typedef enum {
    ICON_TRACE,      // seismogram squiggle
    ICON_SPECTRUM,   // bar chart
    ICON_INFO,       // i in a circle
    ICON_EVENTS,     // list
    ICON_SETTINGS,   // gear-ish
    ICON_WEATHER,    // sun behind cloud
} icon_kind_t;

// WMO weather codes (Open-Meteo) rendered as a simple pictogram.
void icon_draw_weather(lv_color16_t *buf, int16_t w, int16_t h, int wmo_code,
                       lv_color16_t fg, lv_color16_t accent, lv_color16_t bg);

// Fill buf (w*h, RGB565) with the icon in fg on bg.
void icon_draw(lv_color16_t *buf, int16_t w, int16_t h,
               icon_kind_t kind, lv_color16_t fg, lv_color16_t bg);

// Wi-Fi arcs, `level` of 0..3 lit (level < 0 draws a dimmed "no link" glyph).
void icon_draw_wifi(lv_color16_t *buf, int16_t w, int16_t h, int level,
                    lv_color16_t on, lv_color16_t off, lv_color16_t bg);
