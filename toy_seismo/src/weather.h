// Current conditions and a five-day forecast from Open-Meteo.
//
// Fetched DIRECTLY rather than proxied through pi5: no API key is needed, and
// this display is meant to become self-sufficient when the standalone IMU
// replaces the pi5 feed. Metric throughout.
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

// Oakmont, Santa Rosa
#define WX_LAT  38.4405f
#define WX_LON  -122.6190f

#define WX_DAYS 5

struct WxDay {
    int   code;          // WMO weather code
    float tmax, tmin;    // degC
    int   precip_pct;
    char  label[8];      // "Mon", "Tue", ...
};

struct Weather {
    bool  valid;
    // current
    float temp_c, apparent_c, wind_kmh, pressure_hpa;
    int   humidity_pct, code;
    // forecast
    WxDay day[WX_DAYS];
    uint32_t fetched_ms;
};

// Build the request URL. Plain HTTP on purpose -- see weather.cpp.
void weather_url(char *buf, size_t n);

// Parse a fetched body. Runs on the UI task; does no networking.
bool weather_parse(const char *body, Weather *out);

// Short human description for a WMO code.
const char *wx_text(int code);
