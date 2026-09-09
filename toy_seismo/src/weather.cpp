#include "weather.h"
#include <Arduino.h>
#include <HTTPClient.h>
#include "scratch.h"
#include <time.h>

const char *wx_text(int c)
{
    switch (c)
    {
    case 0:  return "Clear";
    case 1:  return "Mainly clear";
    case 2:  return "Partly cloudy";
    case 3:  return "Overcast";
    case 45: case 48: return "Fog";
    case 51: case 53: case 55: return "Drizzle";
    case 56: case 57: return "Freezing drizzle";
    case 61: return "Light rain";
    case 63: return "Rain";
    case 65: return "Heavy rain";
    case 66: case 67: return "Freezing rain";
    case 71: case 73: case 75: case 77: return "Snow";
    case 80: return "Light showers";
    case 81: return "Showers";
    case 82: return "Heavy showers";
    case 85: case 86: return "Snow showers";
    case 95: return "Thunderstorm";
    case 96: case 99: return "Thunderstorm, hail";
    default: return "--";
    }
}

// Minimal extraction on a plain C string. Same reasoning as /v1/live: a JSON
// DOM for this payload would cost more RAM than it saves effort, and the shapes
// are fixed.
static bool num_after(const char *s, const char *key, float *out)
{
    const char *k = strstr(s, key);
    if (!k) return false;
    k += strlen(key);
    while (*k == ':' || *k == ' ' || *k == '"') k++;
    *out = atof(k);
    return true;
}

static int array_after(const char *s, const char *key, float *dst, int max_n)
{
    const char *k = strstr(s, key);
    if (!k) return 0;
    const char *p = strchr(k, '[');
    if (!p) return 0;
    const char *stop = strchr(p, ']');
    if (!stop) return 0;
    int n = 0;
    p++;
    while (p < stop && n < max_n)
    {
        char *nx;
        const float v = strtof(p, &nx);
        if (nx == p) break;
        dst[n++] = v;
        p = nx;
        while (p < stop && (*p == ',' || *p == ' ' || *p == '"')) p++;
    }
    return n;
}

// PLAIN HTTP, not HTTPS, and deliberately so. api.open-meteo.com answers on
// http with no redirect. TLS would cost ~40 KB of CONTIGUOUS INTERNAL SRAM
// (mbedTLS is built with CONFIG_MBEDTLS_INTERNAL_MEM_ALLOC, so PSRAM cannot help
// it) on a board whose largest free internal block is ~18-25 KB once the
// display's bounce buffers are allocated. The first fetch after boot succeeded
// and every one after it failed, leaving stale weather on screen forever.
// Nothing secret is sent -- a latitude and a longitude.
// Do NOT generalise this to anything carrying credentials.
void weather_url(char *buf, size_t n)
{
    snprintf(buf, n,
        "http://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "weather_code,wind_speed_10m,surface_pressure"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max"
        "&timezone=America%%2FLos_Angeles&forecast_days=%d"
        "&temperature_unit=celsius&wind_speed_unit=kmh", WX_LAT, WX_LON, WX_DAYS);
}

bool weather_parse(const char *body, Weather *out)
{
    if (!body || strlen(body) < 64) return false;

    float v;
    const char *cur = strstr(body, "\"current\"");
    if (cur)
    {
        if (num_after(cur, "\"temperature_2m\"", &v))       out->temp_c = v;
        if (num_after(cur, "\"apparent_temperature\"", &v)) out->apparent_c = v;
        if (num_after(cur, "\"relative_humidity_2m\"", &v)) out->humidity_pct = (int)v;
        if (num_after(cur, "\"weather_code\"", &v))         out->code = (int)v;
        if (num_after(cur, "\"wind_speed_10m\"", &v))       out->wind_kmh = v;
        if (num_after(cur, "\"surface_pressure\"", &v))     out->pressure_hpa = v;
    }

    const char *dly = strstr(body, "\"daily\"");
    if (!dly) { log_w("weather: no daily block"); return false; }

    float codes[WX_DAYS], tmax[WX_DAYS], tmin[WX_DAYS], pp[WX_DAYS];
    const int nc = array_after(dly, "\"weather_code\"", codes, WX_DAYS);
    array_after(dly, "\"temperature_2m_max\"", tmax, WX_DAYS);
    array_after(dly, "\"temperature_2m_min\"", tmin, WX_DAYS);
    array_after(dly, "\"precipitation_probability_max\"", pp, WX_DAYS);

    const char *tk = strstr(dly, "\"time\"");
    const char *lb = tk ? strchr(tk, '[') : NULL;
    for (int i = 0; i < WX_DAYS; i++)
    {
        out->day[i].code = (i < nc) ? (int)codes[i] : -1;
        out->day[i].tmax = tmax[i];
        out->day[i].tmin = tmin[i];
        out->day[i].precip_pct = (int)pp[i];
        snprintf(out->day[i].label, sizeof out->day[i].label, "D+%d", i);

        // ISO dates are "YYYY-MM-DD", 13 bytes each including quotes and comma
        if (lb && (int)strlen(lb) > 1 + i * 13 + 11)
        {
            const char *q = lb + 1 + i * 13;
            if (*q == '"')
            {
                struct tm tmv = {};
                char iso[11] = {0};
                memcpy(iso, q + 1, 10);
                tmv.tm_year = atoi(iso) - 1900;
                tmv.tm_mon  = atoi(iso + 5) - 1;
                tmv.tm_mday = atoi(iso + 8);
                tmv.tm_hour = 12;
                const time_t tt = mktime(&tmv);
                struct tm g;
                localtime_r(&tt, &g);
                static const char *dn[7] = {"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
                snprintf(out->day[i].label, sizeof out->day[i].label, "%s", dn[g.tm_wday % 7]);
            }
        }
    }

    out->valid = true;
    out->fetched_ms = millis();
    log_i("weather: %.1f C, code %d, day0 %s %.0f/%.0f",
          out->temp_c, out->code, out->day[0].label, out->day[0].tmax, out->day[0].tmin);
    return true;
}
