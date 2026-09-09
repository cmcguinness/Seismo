// One shared scratch buffer in PSRAM, reserved once at boot.
//
// Every HTTP body we read -- /v1/live (~20 KB), /v1/events, the weather forecast
// -- used to allocate its own. Those fetches never overlap, so they share one
// reservation: no repeated allocation, no churn on the internal heap, and one
// place where the size is decided rather than three separate guesses.
//
// PSRAM deliberately. Internal SRAM is the scarce resource here -- bounce
// buffers (96 KB), LVGL and WiFi all compete for ~62 KB free -- while PSRAM has
// 7 MB idle.
#pragma once
#include <stddef.h>

#define SCRATCH_SIZE (40 * 1024)

bool   scratch_init(void);
char  *scratch(void);          // NULL if unavailable
size_t scratch_size(void);
