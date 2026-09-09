#include "net.h"
#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>
#include "scratch.h"
#include "weather.h"

static SemaphoreHandle_t sem_ready;   // given by net task: a result is waiting
static SemaphoreHandle_t sem_free;    // given by UI: scratch is free again

static volatile NetKind  r_kind = NET_NONE;
static volatile int      r_len  = 0;
static volatile bool     live_ok = true;
static volatile uint32_t n_fetch = 0, n_fail = 0;
static volatile uint32_t t_last = 0, t_worst = 0, t_sum = 0, t_n = 0;

// Chunk size and pause are a BANDWIDTH THROTTLE, not a buffer size. 1 KB every
// 8 ms is ~125 KB/s, far more than the ~5 KB/s this display actually needs, but
// slow enough that the radio never monopolises the bus.
#define NET_CHUNK           1024
#define NET_CHUNK_PAUSE_MS  8

static char s_host[64];
static int  s_port;

// Blocking GET into the shared scratch buffer. Runs ONLY on the network task.
static int http_get_scratch(const char *url, uint32_t connect_ms, uint32_t read_ms)
{
    char *buf = scratch();
    if (!buf) return -1;

    HTTPClient http;
    http.setConnectTimeout(connect_ms);
    http.setTimeout(read_ms);
    http.setReuse(false);          // pi5 is HTTP/1.0 and closes after each reply
    if (!http.begin(url)) return -1;
    if (http.GET() != 200) { http.end(); return -1; }

    int len = http.getSize();
    if (len < 0 || (size_t)len >= scratch_size()) len = scratch_size() - 1;
    WiFiClient *st = http.getStreamPtr();
    // PACED read. Pulling ~19 KB as fast as the radio can deliver it starved
    // the LCD's bounce-buffer refill and striped the top ~100 rows of the frame
    // constantly. The A/B was unambiguous: an idle network task is clean, a busy
    // one is not, and the WiFi buffers are internal so it is the burst itself.
    //
    // Reading in small chunks with a yield between spreads the same bytes over
    // ~200 ms and lets the refill interleave. We are in no hurry -- this runs on
    // its own task and /v1/live carries 30 s of history.
    int got = 0;
    const uint32_t deadline = millis() + read_ms;
    while (got < len && millis() < deadline)
    {
        int want = len - got;
        if (want > NET_CHUNK) want = NET_CHUNK;
        const int n = st->readBytes(buf + got, want);
        if (n <= 0) { if (!st->connected()) break; vTaskDelay(1); continue; }
        got += n;
        vTaskDelay(pdMS_TO_TICKS(NET_CHUNK_PAUSE_MS));
    }
    buf[got] = 0;
    http.end();
    return got;
}

static void net_task(void *)
{
    uint32_t last_live = 0, last_ev = 0, last_wx = 0;
    char url[440];

    for (;;)
    {
#ifdef NET_QUIET
        // A/B control: the task exists, is pinned to core 0, and does nothing.
        // If the display is clean like this and glitches without it, the cause
        // is network TRAFFIC; if it glitches either way, the task is innocent.
        vTaskDelay(pdMS_TO_TICKS(200));
        continue;
#endif
        if (WiFi.status() != WL_CONNECTED) { vTaskDelay(pdMS_TO_TICKS(500)); continue; }

        const uint32_t now = millis();
        NetKind want = NET_NONE;

        // pi5 refreshes its live window in ~5.5 s blocks; back off when the last
        // fetch carried nothing new.
        const uint32_t live_gap = live_ok ? 4000 : 1500;
        if (now - last_live >= live_gap)                   want = NET_LIVE;
        else if (now - last_ev >= 20000)                   want = NET_EVENTS;
        else if (last_wx == 0 || now - last_wx >= 900000UL) want = NET_WEATHER;

        if (want == NET_NONE) { vTaskDelay(pdMS_TO_TICKS(20)); continue; }

        // Wait for the UI to release the shared buffer before overwriting it.
        if (xSemaphoreTake(sem_free, pdMS_TO_TICKS(200)) != pdTRUE) continue;

        const uint32_t t_begin = millis();
        int len = -1;
        switch (want)
        {
        case NET_LIVE:
            last_live = now;
            snprintf(url, sizeof url, "http://%s:%d/v1/live", s_host, s_port);
            len = http_get_scratch(url, 4000, 8000);
            break;
        case NET_EVENTS:
            last_ev = now;
            snprintf(url, sizeof url, "http://%s:%d/v1/events?limit=3", s_host, s_port);
            len = http_get_scratch(url, 4000, 6000);
            break;
        case NET_WEATHER:
            last_wx = now;
            weather_url(url, sizeof url);
            len = http_get_scratch(url, 6000, 9000);
            break;
        default: break;
        }

        const uint32_t took = millis() - t_begin;
        t_last = took;
        if (took > t_worst) t_worst = took;
        t_sum += took; t_n++;

        if (len > 32)
        {
            n_fetch++;
            r_kind = want;
            r_len  = len;
            xSemaphoreGive(sem_ready);          // UI will release when parsed
        }
        else
        {
            n_fail++;
            r_kind = NET_NONE;
            xSemaphoreGive(sem_free);           // nothing to hand over
        }
    }
}

bool net_start(const char *host, int port)
{
    snprintf(s_host, sizeof s_host, "%s", host);
    s_port = port;

    sem_ready = xSemaphoreCreateBinary();
    sem_free  = xSemaphoreCreateBinary();
    if (!sem_ready || !sem_free) return false;
    xSemaphoreGive(sem_free);                   // buffer starts free

    // Core 0: the Arduino loop runs on core 1 (ARDUINO_RUNNING_CORE=1), and the
    // WiFi stack already lives on core 0, so this keeps radio work together and
    // leaves the UI core uncontended.
    return xTaskCreatePinnedToCore(net_task, "net", 6144, NULL, 4, NULL, 0) == pdPASS;
}

NetKind net_poll(const char **body, int *len)
{
    if (xSemaphoreTake(sem_ready, 0) != pdTRUE) return NET_NONE;
    if (body) *body = scratch();
    if (len)  *len  = r_len;
    return r_kind;
}

void net_release(void) { xSemaphoreGive(sem_free); }
void net_live_productive(bool yes) { live_ok = yes; }
uint32_t net_last_ms(void)  { return t_last; }
uint32_t net_worst_ms(void) { return t_worst; }
uint32_t net_mean_ms(void)  { return t_n ? t_sum / t_n : 0; }
void     net_reset_timing(void) { t_worst = 0; t_sum = 0; t_n = 0; }

uint32_t net_fetch_count(void) { return n_fetch; }
uint32_t net_fail_count(void)  { return n_fail; }
