#include "weather.h"
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
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

// Minimal extraction. Same reasoning as /v1/live: a JSON DOM for this payload
// would cost more RAM than it saves effort, and the shapes are fixed.
static bool num_after(const String &s, const char *key, int from, float *out, int *next)
{
    const int k = s.indexOf(key, from);
    if (k < 0) return false;
    int i = k + strlen(key);
    while (i < (int)s.length() && (s[i] == ':' || s[i] == ' ' || s[i] == '"')) i++;
    *out = atof(s.c_str() + i);
    if (next) *next = i;
    return true;
}

static int array_after(const String &s, const char *key, float *dst, int max_n)
{
    const int k = s.indexOf(key);
    if (k < 0) return 0;
    int i = s.indexOf('[', k);
    if (i < 0) return 0;
    const int end = s.indexOf(']', i);
    int n = 0;
    const char *p = s.c_str() + i + 1;
    const char *stop = s.c_str() + end;
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

bool weather_fetch(Weather *out, float lat, float lon)
{
    if (WiFi.status() != WL_CONNECTED) return false;

    WiFiClientSecure *tls = new WiFiClientSecure;
    if (!tls) return false;
    // No cert pinning: this is a public, unauthenticated forecast endpoint and
    // nothing is sent to it but a lat/lon. Worth being explicit that this is a
    // deliberate choice, not an oversight -- do NOT copy it for anything that
    // carries credentials.
    tls->setInsecure();
    tls->setTimeout(8);

    char url[420];
    snprintf(url, sizeof url,
        "https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "weather_code,wind_speed_10m,surface_pressure"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max"
        "&timezone=America%%2FLos_Angeles&forecast_days=%d"
        "&temperature_unit=celsius&wind_speed_unit=kmh", lat, lon, WX_DAYS);

    HTTPClient https;
    https.setConnectTimeout(6000);
    https.setTimeout(9000);
    https.setReuse(false);
    bool ok = false;

    if (https.begin(*tls, url))
    {
        const int code = https.GET();
        if (code == 200)
        {
            String body = https.getString();
            const int cur = body.indexOf("\"current\"");
            float v;
            if (cur >= 0)
            {
                if (num_after(body, "\"temperature_2m\"", cur, &v, NULL)) out->temp_c = v;
                if (num_after(body, "\"apparent_temperature\"", cur, &v, NULL)) out->apparent_c = v;
                if (num_after(body, "\"relative_humidity_2m\"", cur, &v, NULL)) out->humidity_pct = (int)v;
                if (num_after(body, "\"weather_code\"", cur, &v, NULL)) out->code = (int)v;
                if (num_after(body, "\"wind_speed_10m\"", cur, &v, NULL)) out->wind_kmh = v;
                if (num_after(body, "\"surface_pressure\"", cur, &v, NULL)) out->pressure_hpa = v;
            }

            const int dly = body.indexOf("\"daily\"");
            if (dly >= 0)
            {
                String d = body.substring(dly);
                float codes[WX_DAYS], tmax[WX_DAYS], tmin[WX_DAYS], pp[WX_DAYS];
                const int nc = array_after(d, "\"weather_code\"", codes, WX_DAYS);
                array_after(d, "\"temperature_2m_max\"", tmax, WX_DAYS);
                array_after(d, "\"temperature_2m_min\"", tmin, WX_DAYS);
                array_after(d, "\"precipitation_probability_max\"", pp, WX_DAYS);

                // day labels come from the "time" array of ISO dates
                const int t = d.indexOf("\"time\"");
                const int lb = d.indexOf('[', t);
                for (int i = 0; i < WX_DAYS; i++)
                {
                    out->day[i].code = (i < nc) ? (int)codes[i] : -1;
                    out->day[i].tmax = tmax[i];
                    out->day[i].tmin = tmin[i];
                    out->day[i].precip_pct = (int)pp[i];
                    snprintf(out->day[i].label, sizeof out->day[i].label, "D+%d", i);
                    if (lb > 0)
                    {
                        const int q = d.indexOf('"', lb + 1 + i * 13);
                        if (q > 0 && d.length() > (unsigned)(q + 11))
                        {
                            struct tm tmv = {};
                            const String iso = d.substring(q + 1, q + 11);   // YYYY-MM-DD
                            tmv.tm_year = iso.substring(0, 4).toInt() - 1900;
                            tmv.tm_mon  = iso.substring(5, 7).toInt() - 1;
                            tmv.tm_mday = iso.substring(8, 10).toInt();
                            tmv.tm_hour = 12;
                            const time_t tt = mktime(&tmv);
                            struct tm g;
                            localtime_r(&tt, &g);
                            static const char *dn[7] = {"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
                            snprintf(out->day[i].label, sizeof out->day[i].label,
                                     "%s", dn[g.tm_wday % 7]);
                        }
                    }
                }
                ok = true;
            }
        }
        else log_w("weather: HTTP %d", code);
        https.end();
    }
    delete tls;

    if (ok) { out->valid = true; out->fetched_ms = millis(); }
    return ok;
}
