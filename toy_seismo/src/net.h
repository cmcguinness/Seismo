// HTTP fetching on its own task, off the UI thread.
//
// WHY: every fetch used to run inside loop(). /v1/live goes every 2-4 s and the
// weather fetch can sit on its timeouts for seconds, and for that whole time the
// loop never reached display_wait_vsync() or paint_drain() -- so the trace froze
// and touch stopped answering. It looked exactly like a hang. It also defeated
// the playout buffer: no amount of servo smoothing survives a multi-second stall.
//
// The ESP32-S3 has two cores and we were using one. Networking now runs pinned
// to core 0; the UI keeps core 1.
//
// ⚠️ THE RULE THAT MATTERS: LVGL IS NOT THREAD SAFE. The network task touches
// NOTHING but the scratch buffer and plain data. Every lv_* call stays on the UI
// task. The handoff below is deliberately a raw buffer, not a parsed object, so
// there is no temptation to update a label from the wrong core.
#pragma once
#include <stdint.h>
#include <stddef.h>

enum NetKind { NET_NONE = 0, NET_LIVE, NET_EVENTS, NET_WEATHER };

// Start the task. host/port are for the pi5 endpoints.
bool net_start(const char *host, int port);

// UI side: is a result waiting? Returns NET_NONE if not. On a hit, `body` is the
// shared scratch buffer holding a NUL-terminated response of `len` bytes, valid
// until net_release().
NetKind net_poll(const char **body, int *len);

// UI side: finished parsing; hand the buffer back so the next fetch may start.
void net_release(void);

// UI side: tell the scheduler whether the last live fetch actually carried new
// samples, so it can back off when the feed has not moved.
void net_live_productive(bool yes);

uint32_t net_fetch_count(void);
uint32_t net_fail_count(void);
