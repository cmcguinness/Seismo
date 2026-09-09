#include "ui_shell.h"
#include <esp_heap_caps.h>
#include <stdio.h>
#include <math.h>

// palette
static const lv_color_t C_BG     = LV_COLOR_MAKE(0x08, 0x0A, 0x0C);
static const lv_color_t C_BAR    = LV_COLOR_MAKE(0x11, 0x16, 0x1B);
static const lv_color_t C_RAIL   = LV_COLOR_MAKE(0x0D, 0x11, 0x15);
static const lv_color_t C_TEXT   = LV_COLOR_MAKE(0xE8, 0xEE, 0xF2);
static const lv_color_t C_DIM    = LV_COLOR_MAKE(0x6C, 0x7A, 0x85);
static const lv_color_t C_ACCENT = LV_COLOR_MAKE(0x30, 0xE0, 0x60);

static lv_color16_t rgb565_of(uint8_t r, uint8_t g, uint8_t b)
{
    lv_color16_t c; c.red = r >> 3; c.green = g >> 2; c.blue = b >> 3; return c;
}

struct Page {
    lv_obj_t     *content;
    lv_obj_t     *btn;         // rail button
    lv_obj_t     *icon;        // canvas inside the button
    lv_color16_t *icon_buf;
    icon_kind_t   kind;
};

static Page        pages[UI_MAX_PAGES];
static int         n_pages = 0, cur = -1;
static lv_obj_t   *bar, *rail, *lbl_station, *wifi_canvas;
static lv_obj_t   *help_btn, *help_icon, *help_panel, *help_label;
static const char *help_text[UI_MAX_PAGES];
static bool        help_on = false;

// The clock is EIGHT fixed-width cells, not one label. Montserrat is
// proportional -- "1" is much narrower than "8" -- so a single label reflows on
// every digit change and the time visibly squirms. One character per cell, each
// cell a constant width with the glyph centred, makes the colons stand still.
#define CLK_CELLS   8            // HH:MM:SS
#define CLK_CELL_W  19
static lv_obj_t   *clk_cell[CLK_CELLS];
static char        clk_shown[CLK_CELLS + 1] = "        ";
static lv_color16_t *wifi_buf;

#define WIFI_W 34
#define WIFI_H 26

static void repaint_icon(int i, bool active)
{
    if (!pages[i].icon_buf) return;
    icon_draw(pages[i].icon_buf, UI_ICON_PX, UI_ICON_PX, pages[i].kind,
              active ? rgb565_of(0x08, 0x0A, 0x0C) : rgb565_of(0x8F, 0xA0, 0xAC),
              active ? rgb565_of(0x30, 0xE0, 0x60) : rgb565_of(0x0D, 0x11, 0x15));
    lv_obj_invalidate(pages[i].icon);
}

static void help_repaint(void);

static void help_hide(void)
{
    if (!help_on) return;
    help_on = false;
    lv_obj_add_flag(help_panel, LV_OBJ_FLAG_HIDDEN);
    if (cur >= 0) lv_obj_remove_flag(pages[cur].content, LV_OBJ_FLAG_HIDDEN);
    help_repaint();
}

static void on_rail_click(lv_event_t *e)
{
    // Any page icon leaves help and goes to that page.
    help_hide();
    ui_shell_select((int)(intptr_t)lv_event_get_user_data(e));
}

static void on_help_click(lv_event_t *e)
{
    if (help_on) { help_hide(); return; }
    if (cur < 0) return;
    help_on = true;
    lv_label_set_text(help_label, help_text[cur] ? help_text[cur] : "No help for this page.");
    lv_obj_add_flag(pages[cur].content, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(help_panel, LV_OBJ_FLAG_HIDDEN);
    help_repaint();
}

// The "?" is drawn, not a glyph, to match the other icons.
// A real glyph on a rounded plate. The hand-drawn arc version was too abstract
// to read as a question mark at 56 px -- the other icons are shapes by nature,
// but "?" is a character and looks wrong reconstructed from primitives.
static void help_repaint(void)
{
    if (!help_icon) return;
    lv_obj_set_style_bg_color(help_icon,
        help_on ? lv_color_hex(0xFFC040) : lv_color_hex(0x1A2027), LV_PART_MAIN);
    lv_obj_set_style_text_color(help_icon,
        help_on ? lv_color_hex(0x080A0C) : lv_color_hex(0x8FA0AC), LV_PART_MAIN);
}

void ui_shell_init(lv_obj_t *screen)
{
    lv_obj_set_style_bg_color(screen, C_BG, LV_PART_MAIN);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

    // ---- title bar ----
    bar = lv_obj_create(screen);
    lv_obj_set_size(bar, LV_HOR_RES, UI_BAR_H);
    lv_obj_set_pos(bar, 0, 0);
    lv_obj_set_style_bg_color(bar, C_BAR, LV_PART_MAIN);
    lv_obj_set_style_border_width(bar, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(bar, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(bar, 0, LV_PART_MAIN);
    lv_obj_remove_flag(bar, LV_OBJ_FLAG_SCROLLABLE);

    lbl_station = lv_label_create(bar);
    lv_label_set_text(lbl_station, "");
    lv_obj_set_style_text_color(lbl_station, C_TEXT, LV_PART_MAIN);
    lv_obj_set_style_text_font(lbl_station, &lv_font_montserrat_24, LV_PART_MAIN);
    lv_obj_align(lbl_station, LV_ALIGN_LEFT_MID, 14, 0);

    // "HH:MM:SS" in fixed cells, then a static "UTC" that never changes.
    const int total = CLK_CELLS * CLK_CELL_W;
    for (int i = 0; i < CLK_CELLS; i++)
    {
        clk_cell[i] = lv_label_create(bar);
        lv_label_set_text(clk_cell[i], "-");
        lv_obj_set_width(clk_cell[i], CLK_CELL_W);
        lv_obj_set_style_text_align(clk_cell[i], LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
        lv_obj_set_style_text_color(clk_cell[i], C_TEXT, LV_PART_MAIN);
        lv_obj_set_style_text_font(clk_cell[i], &lv_font_montserrat_28, LV_PART_MAIN);
        lv_obj_align(clk_cell[i], LV_ALIGN_CENTER,
                     -total / 2 - 22 + i * CLK_CELL_W, 0);
    }
    lv_obj_t *utc = lv_label_create(bar);
    lv_label_set_text(utc, "UTC");
    lv_obj_set_style_text_color(utc, C_DIM, LV_PART_MAIN);
    lv_obj_align(utc, LV_ALIGN_CENTER, total / 2 - 12, 2);

    wifi_buf = (lv_color16_t *)heap_caps_malloc(WIFI_W * WIFI_H * 2, MALLOC_CAP_SPIRAM);
    if (wifi_buf)
    {
        wifi_canvas = lv_canvas_create(bar);
        lv_canvas_set_buffer(wifi_canvas, wifi_buf, WIFI_W, WIFI_H, LV_COLOR_FORMAT_RGB565);
        lv_obj_align(wifi_canvas, LV_ALIGN_RIGHT_MID, -16, 0);
        ui_shell_set_wifi(0, false);
    }

    // ---- icon rail ----
    rail = lv_obj_create(screen);
    lv_obj_set_size(rail, UI_RAIL_W, LV_VER_RES - UI_BAR_H);
    lv_obj_set_pos(rail, 0, UI_BAR_H);
    lv_obj_set_style_bg_color(rail, C_RAIL, LV_PART_MAIN);
    lv_obj_set_style_border_width(rail, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(rail, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(rail, 0, LV_PART_MAIN);
    lv_obj_remove_flag(rail, LV_OBJ_FLAG_SCROLLABLE);

    // ---- help panel (overlays the content area) ----
    help_panel = lv_obj_create(screen);
    lv_obj_set_size(help_panel, ui_content_w(), ui_content_h());
    lv_obj_set_pos(help_panel, UI_RAIL_W, UI_BAR_H);
    lv_obj_set_style_bg_color(help_panel, lv_color_hex(0x0F141A), LV_PART_MAIN);
    lv_obj_set_style_border_width(help_panel, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(help_panel, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(help_panel, 0, LV_PART_MAIN);
    lv_obj_remove_flag(help_panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(help_panel, LV_OBJ_FLAG_HIDDEN);

    help_label = lv_label_create(help_panel);
    lv_label_set_long_mode(help_label, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(help_label, ui_content_w() - 32);
    lv_obj_set_style_text_color(help_label, C_TEXT, LV_PART_MAIN);
    lv_obj_set_style_text_font(help_label, &lv_font_montserrat_18, LV_PART_MAIN);
    lv_obj_align(help_label, LV_ALIGN_TOP_LEFT, 16, 14);

    // ---- "?" pinned at the BOTTOM of the rail ----
    help_btn = lv_obj_create(rail);
    lv_obj_set_size(help_btn, UI_ICON_PX + 8, UI_ICON_PX + 8);
    lv_obj_align(help_btn, LV_ALIGN_BOTTOM_MID, 0, -14);
    lv_obj_set_style_bg_opa(help_btn, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(help_btn, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(help_btn, 0, LV_PART_MAIN);
    lv_obj_remove_flag(help_btn, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(help_btn, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(help_btn, on_help_click, LV_EVENT_CLICKED, NULL);

    help_icon = lv_label_create(help_btn);
    lv_label_set_text(help_icon, "?");
    lv_obj_set_style_text_font(help_icon, &lv_font_montserrat_48, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(help_icon, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_radius(help_icon, 12, LV_PART_MAIN);
    lv_obj_set_style_pad_hor(help_icon, 16, LV_PART_MAIN);
    lv_obj_set_style_pad_ver(help_icon, 2, LV_PART_MAIN);
    lv_obj_center(help_icon);
    lv_obj_remove_flag(help_icon, LV_OBJ_FLAG_CLICKABLE);
    help_repaint();
}

void ui_shell_set_help(int page_index, const char *text)
{
    if (page_index >= 0 && page_index < UI_MAX_PAGES) help_text[page_index] = text;
}

bool ui_shell_help_visible(void) { return help_on; }

int16_t ui_content_w(void) { return (int16_t)(LV_HOR_RES - UI_RAIL_W); }
int16_t ui_content_h(void) { return (int16_t)(LV_VER_RES - UI_BAR_H); }

lv_obj_t *ui_shell_add_page(icon_kind_t icon, const char *a11y_name)
{
    if (n_pages >= UI_MAX_PAGES) return NULL;
    const int i = n_pages++;

    Page &p = pages[i];
    p.kind = icon;

    p.content = lv_obj_create(lv_obj_get_parent(rail));
    lv_obj_set_size(p.content, ui_content_w(), ui_content_h());
    lv_obj_set_pos(p.content, UI_RAIL_W, UI_BAR_H);
    lv_obj_set_style_bg_color(p.content, C_BG, LV_PART_MAIN);
    lv_obj_set_style_border_width(p.content, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(p.content, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(p.content, 0, LV_PART_MAIN);
    lv_obj_remove_flag(p.content, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(p.content, LV_OBJ_FLAG_HIDDEN);

    p.btn = lv_obj_create(rail);
    lv_obj_set_size(p.btn, UI_ICON_PX + 8, UI_ICON_PX + 8);
    lv_obj_set_pos(p.btn, (UI_RAIL_W - UI_ICON_PX - 8) / 2, 14 + i * (UI_ICON_PX + 22));
    lv_obj_set_style_bg_opa(p.btn, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(p.btn, 0, LV_PART_MAIN);
    lv_obj_set_style_pad_all(p.btn, 0, LV_PART_MAIN);
    lv_obj_set_style_radius(p.btn, 10, LV_PART_MAIN);
    lv_obj_remove_flag(p.btn, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(p.btn, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(p.btn, on_rail_click, LV_EVENT_CLICKED, (void *)(intptr_t)i);

    p.icon_buf = (lv_color16_t *)heap_caps_malloc(UI_ICON_PX * UI_ICON_PX * 2,
                                                  MALLOC_CAP_SPIRAM);
    if (p.icon_buf)
    {
        p.icon = lv_canvas_create(p.btn);
        lv_canvas_set_buffer(p.icon, p.icon_buf, UI_ICON_PX, UI_ICON_PX,
                             LV_COLOR_FORMAT_RGB565);
        lv_obj_center(p.icon);
        // the icon canvas must not swallow the button's touch events
        lv_obj_remove_flag(p.icon, LV_OBJ_FLAG_CLICKABLE);
        repaint_icon(i, false);
    }

    if (cur < 0) ui_shell_select(0);
    return p.content;
}

void ui_shell_select(int index)
{
    if (index < 0 || index >= n_pages || index == cur) return;
    if (cur >= 0)
    {
        lv_obj_add_flag(pages[cur].content, LV_OBJ_FLAG_HIDDEN);
        repaint_icon(cur, false);
    }
    cur = index;
    if (!help_on) lv_obj_remove_flag(pages[cur].content, LV_OBJ_FLAG_HIDDEN);
    repaint_icon(cur, true);
}

int ui_shell_current(void) { return cur; }

void ui_shell_set_station(const char *s) { lv_label_set_text(lbl_station, s); }

// Expects at least 8 chars of "HH:MM:SS". Only cells whose character actually
// changed are touched -- one or two per second instead of eight, so the title
// bar contributes almost nothing to the PSRAM traffic budget.
void ui_shell_set_clock(const char *s)
{
    if (!s) return;
    for (int i = 0; i < CLK_CELLS && s[i]; i++)
    {
        if (s[i] == clk_shown[i]) continue;
        clk_shown[i] = s[i];
        const char c[2] = {s[i], 0};
        lv_label_set_text(clk_cell[i], c);
    }
}

void ui_shell_set_wifi(int rssi_dbm, bool linked)
{
    if (!wifi_buf) return;
    // -55 or better = full, -80 or worse = one bar. Repaint only on change, so
    // the title bar is not a source of per-second PSRAM traffic.
    int level = -1;
    if (linked)
    {
        if      (rssi_dbm >= -55) level = 3;
        else if (rssi_dbm >= -67) level = 2;
        else if (rssi_dbm >= -78) level = 1;
        else                      level = 0;
    }
    static int last = -99;
    if (level == last) return;
    last = level;

    icon_draw_wifi(wifi_buf, WIFI_W, WIFI_H, level,
                   rgb565_of(0x30, 0xE0, 0x60), rgb565_of(0x2A, 0x33, 0x3A),
                   rgb565_of(0x11, 0x16, 0x1B));
    lv_obj_invalidate(wifi_canvas);
}
