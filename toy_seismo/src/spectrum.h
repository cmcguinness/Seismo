// Minimal radix-2 FFT for the live spectrum panel.
//
// 256 points at 100 sps -> 0.391 Hz bins, 0-50 Hz. That resolution is chosen to
// separate the station's documented lines (CLAUDE.md): the 41 / 40.6 / 37.65 Hz
// heat-pump cluster, the 40.0 Hz mains alias, 19.3 / 20 Hz, and the 1.05 Hz one
// that is still unexplained. Anything coarser merges the heat-pump cluster into
// a single smear and the display stops teaching anything.
#pragma once
#include <math.h>

#define FFT_N     256
#define FFT_BINS  (FFT_N / 2)

// In-place iterative radix-2 decimation-in-time. re[]/im[] are FFT_N long.
static void fft_run(float *re, float *im)
{
    // bit-reversal permutation
    for (int i = 1, j = 0; i < FFT_N; i++)
    {
        int bit = FFT_N >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t;
                     t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (int len = 2; len <= FFT_N; len <<= 1)
    {
        const float ang = -2.0f * (float)M_PI / (float)len;
        const float wr = cosf(ang), wi = sinf(ang);
        for (int i = 0; i < FFT_N; i += len)
        {
            float cr = 1.0f, ci = 0.0f;
            for (int k = 0; k < len / 2; k++)
            {
                const int a = i + k, b = i + k + len / 2;
                const float xr = re[b] * cr - im[b] * ci;
                const float xi = re[b] * ci + im[b] * cr;
                re[b] = re[a] - xr; im[b] = im[a] - xi;
                re[a] += xr;        im[a] += xi;
                const float nr = cr * wr - ci * wi;
                ci = cr * wi + ci * wr; cr = nr;
            }
        }
    }
}

// Hann-windowed magnitude spectrum in dB relative to 1 µV.
// Hann, not rectangular: the spectral lines we care about are narrow and strong,
// and rectangular leakage would bury the quiet bins between them in sidelobes.
static void spectrum_db(const float *samples, float *out_db)
{
    static float re[FFT_N], im[FFT_N];
    float mean = 0.0f;
    for (int i = 0; i < FFT_N; i++) mean += samples[i];
    mean /= FFT_N;

    for (int i = 0; i < FFT_N; i++)
    {
        const float w = 0.5f * (1.0f - cosf(2.0f * (float)M_PI * i / (FFT_N - 1)));
        re[i] = (samples[i] - mean) * w;   // de-mean first: DC would dominate bin 0
        im[i] = 0.0f;
    }
    fft_run(re, im);

    for (int k = 0; k < FFT_BINS; k++)
    {
        const float mag = sqrtf(re[k] * re[k] + im[k] * im[k]) * (2.0f / FFT_N);
        out_db[k] = 20.0f * log10f(mag > 1e-6f ? mag : 1e-6f);
    }
}
