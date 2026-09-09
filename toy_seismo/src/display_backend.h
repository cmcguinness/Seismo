// Chooses the display backend. Two exist because the IDF 4.4 one cannot be
// fixed: see README, "the sync-loss investigation".
//
//   default            -> esp32_smartdisplay (lib/), Arduino 2.0.17 / IDF 4.4
//   USE_ESP_LCD_DIRECT -> esp_lcd straight, Arduino 3.3.11 / IDF 5.5
//
// Both expose the same two entry points so the application does not care.
#pragma once

#ifdef USE_ESP_LCD_DIRECT
  #include <lvgl.h>
  void  smartdisplay_init(void);
  void  smartdisplay_lcd_set_backlight(float duty);   // 0..1
  // Ask the RGB peripheral to resynchronise. CONFIG_LCD_RGB_RESTART_IN_VSYNC is
  // enabled in this framework so recovery is automatic, but this is the manual
  // lever if it is ever needed.
  void  display_restart_panel(void);
  // Blocks until the panel enters vertical blanking. During blanking the RGB
  // peripheral fetches NO framebuffer data, so the PSRAM bus is entirely free.
  // With VSYNC_FRONT_PORCH=484 against 480 active lines, that is ~half of every
  // frame -- roughly 25 ms at 20 fps. Drawing inside that window never competes
  // with the scanout at all.
  bool  display_wait_vsync(uint32_t timeout_ms);

  // GLITCH METER. The vsync callback and the bounce-buffer refill ISR both run
  // from flash (CONFIG_LCD_RGB_ISR_IRAM_SAFE is unset), so both are delayed by
  // the same contention. Jitter in vsync arrival is therefore a measurable proxy
  // for the condition that starves the refill and stripes the frame -- which the
  // pixels themselves are not, from inside the firmware.
  //
  // "late" = a frame interval more than 20% past nominal.
  uint32_t display_late_frames(void);   // cumulative
  uint32_t display_total_frames(void);
  uint32_t display_worst_us(void);      // worst interval seen
  void     display_reset_stats(void);
#else
  #include <esp32_smartdisplay.h>
  static inline void display_restart_panel(void) {}   // no such API on IDF 4.4
  static inline bool display_wait_vsync(uint32_t) { return false; }
  static inline uint32_t display_late_frames(void)  { return 0; }
  static inline uint32_t display_total_frames(void) { return 0; }
  static inline uint32_t display_worst_us(void)     { return 0; }
  static inline void     display_reset_stats(void)  {}
#endif
