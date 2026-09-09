// IDF 5.x display backend: esp_lcd RGB panel + LVGL, with the two things
// IDF 4.4 does not have and that this panel provably needs.
//
//   bounce_buffer_size_px -- the LCD peripheral scans out of two small
//     internal-SRAM buffers that an interrupt refills from the PSRAM
//     framebuffer. Espressif: the bounce buffers are larger than the EDMA
//     FIFOs, so this is "more robust against short bandwidth spikes". Those
//     spikes are what desynced the IDF 4.4 build into a permanently shifted
//     image, and eventually into a dead scanout.
//
//   esp_lcd_rgb_panel_restart() + CONFIG_LCD_RGB_RESTART_IN_VSYNC (already =1
//     in this framework) -- if it desyncs anyway, the driver restarts DMA at
//     the next VBlank instead of hanging until someone pulls the USB cable.
//
// Pin assignment and timings come from the board definition, and the
// data_gpio_nums ORDER is copied verbatim from esp32_smartdisplay because the
// colour order was verified correct on hardware with it.

#ifdef USE_ESP_LCD_DIRECT

#include <Arduino.h>
#include <lvgl.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_panel_rgb.h>
#include <esp_heap_caps.h>
#include "display_backend.h"
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

static esp_lcd_panel_handle_t panel = NULL;
static SemaphoreHandle_t vsync_sem = NULL;

static bool IRAM_ATTR on_vsync(esp_lcd_panel_handle_t p,
                               const esp_lcd_rgb_panel_event_data_t *ev, void *ctx)
{
    BaseType_t hp = pdFALSE;
    if (vsync_sem) xSemaphoreGiveFromISR(vsync_sem, &hp);
    return hp == pdTRUE;
}

bool display_wait_vsync(uint32_t timeout_ms)
{
    if (!vsync_sem) return false;
    return xSemaphoreTake(vsync_sem, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}

// 10 lines of draw buffer in INTERNAL DMA-capable SRAM. Rendering happens in
// fast memory; only the finished strip crosses to the PSRAM framebuffer.
//
// The size is a LATENCY budget, not a memory one. Measured on this board the
// SRAM->PSRAM path runs at 28.6 MB/s, so a flush strip of 800 x N x 2 bytes
// holds the bus for N x 56 us. The panel needs a fresh line every ~104 us and
// the bounce buffers cover ~3 ms, so any single operation should stay well
// under 1 ms: 20 lines was 32 KB / 1.1 ms (over budget), 10 lines is 16 KB /
// 0.56 ms. This is the largest single memory operation in the system.
#define DRAW_LINES 10

// Lines per bounce buffer; two are allocated, both in internal SRAM.
//
// 10 was Espressif's suggested starting point and produced visible horizontal
// stripe noise in the top ~100 rows -- the signature of the refill ISR failing
// to keep ahead of the scanout, with RESTART_IN_VSYNC then recovering at the
// top of the frame. It has to be bigger here because
// CONFIG_LCD_RGB_ISR_IRAM_SAFE is NOT set in the precompiled Arduino libs, so
// the refill ISR stalls whenever the flash cache is disabled and needs enough
// buffered lines to ride that out.
//
// Must divide the frame evenly: 800 x 480 = 384000 px, 800 x 30 = 24000, and
// 384000 / 24000 = 16 exactly.
#define BOUNCE_LINES 30

static void flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map)
{
    esp_lcd_panel_draw_bitmap(panel, area->x1, area->y1,
                              area->x2 + 1, area->y2 + 1, px_map);
    lv_display_flush_ready(disp);
}

void display_restart_panel(void)
{
    if (panel) esp_lcd_rgb_panel_restart(panel);
}

void smartdisplay_lcd_set_backlight(float duty)
{
    if (duty < 0) duty = 0;
    if (duty > 1) duty = 1;
    ledcWrite(DISPLAY_BCKL, (uint32_t)(duty * 255.0f));
}

void smartdisplay_init(void)
{
    pinMode(DISPLAY_BCKL, OUTPUT);
    digitalWrite(DISPLAY_BCKL, LOW);
    ledcAttach(DISPLAY_BCKL, 5000, 8);

    esp_lcd_rgb_panel_config_t cfg = {};
    cfg.clk_src    = (lcd_clock_source_t)ST7262_PANEL_CONFIG_CLK_SRC;
    cfg.data_width = ST7262_PANEL_CONFIG_DATA_WIDTH;
    cfg.num_fbs    = 1;
    cfg.bounce_buffer_size_px = ST7262_PANEL_CONFIG_TIMINGS_H_RES * BOUNCE_LINES;
    cfg.psram_trans_align = ST7262_PANEL_CONFIG_PSRAM_TRANS_ALIGN;
    cfg.sram_trans_align  = ST7262_PANEL_CONFIG_SRAM_TRANS_ALIGN;

    cfg.hsync_gpio_num = ST7262_PANEL_CONFIG_HSYNC;
    cfg.vsync_gpio_num = ST7262_PANEL_CONFIG_VSYNC;
    cfg.de_gpio_num    = ST7262_PANEL_CONFIG_DE;
    cfg.pclk_gpio_num  = ST7262_PANEL_CONFIG_PCLK;
    cfg.disp_gpio_num  = ST7262_PANEL_CONFIG_DISP;

    const int pins[16] = {
        ST7262_PANEL_CONFIG_DATA_R0, ST7262_PANEL_CONFIG_DATA_R1,
        ST7262_PANEL_CONFIG_DATA_R2, ST7262_PANEL_CONFIG_DATA_R3,
        ST7262_PANEL_CONFIG_DATA_R4,
        ST7262_PANEL_CONFIG_DATA_G0, ST7262_PANEL_CONFIG_DATA_G1,
        ST7262_PANEL_CONFIG_DATA_G2, ST7262_PANEL_CONFIG_DATA_G3,
        ST7262_PANEL_CONFIG_DATA_G4, ST7262_PANEL_CONFIG_DATA_G5,
        ST7262_PANEL_CONFIG_DATA_B0, ST7262_PANEL_CONFIG_DATA_B1,
        ST7262_PANEL_CONFIG_DATA_B2, ST7262_PANEL_CONFIG_DATA_B3,
        ST7262_PANEL_CONFIG_DATA_B4};
    for (int i = 0; i < 16; i++) cfg.data_gpio_nums[i] = pins[i];

    cfg.timings.pclk_hz           = ST7262_PANEL_CONFIG_TIMINGS_PCLK_HZ;
    cfg.timings.h_res             = ST7262_PANEL_CONFIG_TIMINGS_H_RES;
    cfg.timings.v_res             = ST7262_PANEL_CONFIG_TIMINGS_V_RES;
    cfg.timings.hsync_pulse_width = ST7262_PANEL_CONFIG_TIMINGS_HSYNC_PULSE_WIDTH;
    cfg.timings.hsync_back_porch  = ST7262_PANEL_CONFIG_TIMINGS_HSYNC_BACK_PORCH;
    cfg.timings.hsync_front_porch = ST7262_PANEL_CONFIG_TIMINGS_HSYNC_FRONT_PORCH;
    cfg.timings.vsync_pulse_width = ST7262_PANEL_CONFIG_TIMINGS_VSYNC_PULSE_WIDTH;
    cfg.timings.vsync_back_porch  = ST7262_PANEL_CONFIG_TIMINGS_VSYNC_BACK_PORCH;
    cfg.timings.vsync_front_porch = ST7262_PANEL_CONFIG_TIMINGS_VSYNC_FRONT_PORCH;
    cfg.timings.flags.hsync_idle_low  = ST7262_PANEL_CONFIG_TIMINGS_FLAGS_HSYNC_IDLE_LOW;
    cfg.timings.flags.vsync_idle_low  = ST7262_PANEL_CONFIG_TIMINGS_FLAGS_VSYNC_IDLE_LOW;
    cfg.timings.flags.de_idle_high    = ST7262_PANEL_CONFIG_TIMINGS_FLAGS_DE_IDLE_HIGH;
    cfg.timings.flags.pclk_active_neg = ST7262_PANEL_CONFIG_TIMINGS_FLAGS_PCLK_ACTIVE_NEG;
    cfg.timings.flags.pclk_idle_high  = ST7262_PANEL_CONFIG_TIMINGS_FLAGS_PCLK_IDLE_HIGH;

    cfg.flags.fb_in_psram     = 1;
    cfg.flags.disp_active_low = ST7262_PANEL_CONFIG_FLAGS_DISP_ACTIVE_LOW;

    ESP_ERROR_CHECK(esp_lcd_new_rgb_panel(&cfg, &panel));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel));

    vsync_sem = xSemaphoreCreateBinary();
    esp_lcd_rgb_panel_event_callbacks_t cbs = {};
    cbs.on_vsync = on_vsync;
    ESP_ERROR_CHECK(esp_lcd_rgb_panel_register_event_callbacks(panel, &cbs, NULL));

    log_i("RGB panel up: %dx%d, pclk %d Hz, bounce %u px, num_fbs %u",
          (int)cfg.timings.h_res, (int)cfg.timings.v_res,
          (int)cfg.timings.pclk_hz, (unsigned)cfg.bounce_buffer_size_px,
          (unsigned)cfg.num_fbs);

    lv_init();
    lv_display_t *disp = lv_display_create(ST7262_PANEL_CONFIG_TIMINGS_H_RES,
                                           ST7262_PANEL_CONFIG_TIMINGS_V_RES);
    const size_t buf_px = ST7262_PANEL_CONFIG_TIMINGS_H_RES * DRAW_LINES;
    void *buf = heap_caps_malloc(buf_px * 2, MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA);
    if (!buf) { log_e("draw buffer would not allocate"); return; }
    lv_display_set_buffers(disp, buf, NULL, buf_px * 2, LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_flush_cb(disp, flush_cb);
}

#endif  // USE_ESP_LCD_DIRECT
