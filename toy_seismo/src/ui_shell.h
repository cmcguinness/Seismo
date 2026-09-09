// Reusable application shell: fixed title bar, left icon rail, content area.
//
//   +--------------------------------------------------+
//   | STATION            12:34:56 UTC            ((o))  |  title bar
//   +----+---------------------------------------------+
//   | [] |                                             |
//   | [] |             content (one page)              |  icon rail + pages
//   | [] |                                             |
//   +----+---------------------------------------------+
//
// Deliberately generic -- it knows nothing about seismometers. Pages are plain
// LVGL containers the caller fills.
//
// PAGES ARE BUILT ONCE AND SHOWN/HIDDEN, never rebuilt. On this hardware the
// framebuffer lives in PSRAM and a large single repaint desyncs the panel's
// scanout, so rebuilding a page's canvases on every tap would be a ~610 KB
// burst. Hiding and showing costs one content-area invalidate, which LVGL
// already splits into draw-buffer-sized strips inside the latency budget.
#pragma once
#include <lvgl.h>
#include "ui_icons.h"

#define UI_MAX_PAGES   5
#define UI_BAR_H       52
#define UI_RAIL_W      80
#define UI_ICON_PX     56

void      ui_shell_init(lv_obj_t *screen);

// Returns the page's content container, or NULL if full. Fill it with anything.
lv_obj_t *ui_shell_add_page(icon_kind_t icon, const char *a11y_name);

void      ui_shell_select(int index);

// Context help. Register per-page text; a "?" pinned at the BOTTOM of the rail
// toggles it over the content area. Pressing "?" again, or any page icon,
// returns to the page.
void      ui_shell_set_help(int page_index, const char *text);
bool      ui_shell_help_visible(void);
int       ui_shell_current(void);

// Tap the title bar to fire this. Generic on purpose -- the shell knows nothing
// about what the mark means.
void      ui_shell_set_mark_cb(void (*cb)(void));

void      ui_shell_set_station(const char *s);
void      ui_shell_set_clock(const char *s);
// rssi_dbm, or 1 for "no link". Mapped to 0..3 bars.
void      ui_shell_set_wifi(int rssi_dbm, bool linked);

// Content geometry, so pages can size canvases to fit.
int16_t   ui_content_w(void);
int16_t   ui_content_h(void);
