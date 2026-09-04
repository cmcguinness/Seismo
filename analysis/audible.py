#!/usr/bin/env python3
"""audible.py -- what the station recorded in the band a person can HEAR.

Written the morning of 2026-09-03, when the M3.5 3 km ESE of Larkfield-Wikiup was
heard as a sound -- not just felt -- by people around Santa Rosa, this household
included. An audible earthquake is a real and well-documented thing: ground motion
above roughly 20 Hz couples into the air directly, and close shallow events are the
ones that still have energy up there by the time they arrive. This one was 12.4 km
away and 7.4 km deep, which is about as favourable as our siting gets.

So: is the sound people heard actually IN our data?

THREE CEILINGS SIT BETWEEN THE GROUND AND THE ANSWER, and they are different things:

  50 Hz   Nyquist. We sample at 100 sps, so this is a hard wall -- nothing above it
          exists in the archive at all, and the audible band runs a long way past it.
          Whatever we show here is the BOTTOM of what was heard.

  25 Hz   analysis/specgram.py's FMAX_HZ. This is the one that actually hides things:
          every standard spectrogram in this project crops at 25 Hz, so half of our
          real bandwidth has simply never been plotted. draw() computes the full band
          and only sets ylim, so raising it is free -- this file does exactly that.

  ~-20 dB the ADS1256's own decimation filter. The chip is run at DRATE=100 sps
          (station/adsreader/adsreader.c), so its sinc^5 response has its first notch
          at 100 Hz and is already rolling off well before Nyquist: -6.6 dB at 30 Hz,
          -12.1 dB at 40 Hz, -19.6 dB at 50 Hz. Amplitudes in exactly the band we care
          about are therefore UNDER-reported, and the correction is plotted so the
          under-reporting is visible rather than implied.

AND ONE CONTAMINANT. The 41 / 40.6 / 40.0 / 37.65 / 20 / 19.3 Hz lines are the house's
heat-pump AC and the 60 Hz mains alias, per CLAUDE.md -- they live squarely in the band
this file exists to look at. They are drawn as markers so that nobody (me, later)
mistakes a compressor for a P wave. The test for real signal is TRANSIENCE: an event
arrives and decays over seconds, the HVAC lines are there before and after.

    analysis/.venv/bin/python analysis/audible.py --origin 2026-09-03T17:33:27Z
"""
import argparse
import os
import sys

import numpy as np
from matplotlib import pyplot as plt
from scipy.io import wavfile
from scipy.signal import butter, resample_poly, sosfiltfilt, welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import specgram                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "analysis", "data")
OUT = os.path.join(ROOT, "reports")

# PGA 64, +/-2.5 V reference, 24-bit bipolar -- the same conversion eventcheck.py uses.
UV_PER_COUNT = (2.5 * 2 / (64 * (2 ** 23 - 1))) * 1e6

# Known non-seismic lines (CLAUDE.md): heat-pump AC, plus the 60 Hz mains alias.
HVAC_HZ = [19.3, 20.0, 37.65, 40.6, 41.0]
MAINS_ALIAS_HZ = 40.0

AUDIBLE_LO = 20.0       # conventional bottom of human hearing
HP_HZ = 0.7             # same as specgram.py: kill DC and tilt, keep everything else


def sinc5_response(f, fdata=100.0):
    """The ADS1256's decimation filter, |sinc(f/fdata)|^5. Unity at DC, first notch at
    the data rate. This is why a 40 Hz amplitude read off the archive is about a
    quarter of the 40 Hz amplitude that was actually in the ground."""
    x = np.asarray(f, dtype=float) / fdata
    s = np.where(x == 0, 1.0, np.sinc(x))     # np.sinc is sin(pi x)/(pi x)
    return np.abs(s) ** 5


def undo_sinc5(x, fs, max_db=20.0):
    """Divide the ADC's decimation filter back out -- pre-emphasis, in the frequency
    domain, zero-phase.

    THIS IS LEGITIMATE HERE AND IT IS WORTH SAYING WHY, because "boost the top end
    until it looks better" is the same operation performed for a bad reason. Undoing a
    filter is only honest when you know the filter is the ONLY thing shaping the band,
    and in 20-50 Hz we do:

      - the ADS1256 sinc^5 decimation filter: -6.6 dB at 30 Hz, -19.6 dB at 50. This is
        what we are removing, and it is an exact analytic response, not a fit.
      - the analog front-end RC is deliberately at ~1.7-8 kHz (doc/rev2-frontend.md --
        a true 30 Hz analog corner would need ~25 k series R and wreck the noise floor),
        so it contributes nothing here.
      - a 4.5 Hz geophone is flat in VELOCITY everywhere above f0, so the sensor is not
        shaping this band either.

    Nothing else is in the way, so the correction restores ground motion rather than
    inventing it. It does NOT improve signal-to-noise by one dB: signal and noise are
    boosted by exactly the same gain at each frequency, so a 16x band stays 16x. What
    it fixes is AMPLITUDE -- the archive under-reports 40 Hz by a factor of four, and
    any number read off an uncorrected plot inherits that.

    max_db caps the boost. The inverse diverges at the sinc notch (100 Hz), and while
    Nyquist only needs 19.6 dB, the cap keeps a future change of sample rate from
    quietly turning this into a noise amplifier.
    """
    n = len(x)
    f = np.fft.rfftfreq(n, d=1.0 / fs)
    g = np.minimum(1.0 / np.maximum(sinc5_response(f, fs), 1e-12), 10 ** (max_db / 20.0))
    return np.fft.irfft(np.fft.rfft(x) * g, n=n)


def band_rms(x, fs, lo, hi):
    ny = fs / 2.0
    hi = min(hi, ny * 0.999)
    sos = butter(4, [lo / ny, hi / ny], btype="band", output="sos")
    return sosfiltfilt(sos, x)


# 8 kHz, not the reflexive 44.1. Everything in these clips is below 50 Hz, so 44.1 kHz
# oversamples the content by a factor of 440 and produces a 7 MB file for 85 seconds of
# bass -- in a repo, forever, four times over. 8 kHz still leaves a 4 kHz Nyquist, which
# is eighty times the highest frequency present, and every player on earth reads it.
#
# What matters is not the rate but that it is an exact multiple of 100 sps, so the
# resampling is a clean 80:1 and one second of ground motion is one second of sound at
# the pitch it actually had. That is the property that makes these clips honest.
WAV_SR = 8000


def write_wav(uv, fs, t, label):
    """A REAL-TIME clip of the audible band.

    This is the one sonification on this project that is not a lie about pitch. Every
    other clip we make has to be sped up, because a 1-10 Hz signal is below hearing and
    playing it at true speed produces silence. This event put real energy at 20-50 Hz,
    which is IN the hearing range, so it can be played at 1:1 -- and what comes out is
    (the bottom of) the sound people actually heard, at the frequency they heard it.

    Two honest caveats, both worth saying out loud before anyone concludes the station
    "recorded the sound":

      - It is band-limited at 50 Hz by Nyquist, and the real sound ran well above that.
        This is the fundamental of a boom with every overtone shaved off.
      - It is 20-50 Hz, which is the bottom octave and a half of hearing. Laptop and
        phone speakers cannot reproduce it AT ALL -- they roll off around 150 Hz. On
        those it will be silence, and that is the speaker, not the data. Headphones or
        anything with a woofer will play it.
    """
    # TWO clips, because "what was audible" has two defensible readings and they sound
    # different. The band-limited one applies MY 20 Hz cut and is the cleaner listen.
    # The full-band one applies none and lets the ear do its own filtering, which is
    # what actually happened this morning -- nobody's cochlea was handed a 20 Hz
    # Butterworth. It is the more honest artefact and the quieter one: its peak is set
    # by 1-15 Hz content nothing can reproduce, so normalising to that peak leaves the
    # part you CAN hear about 5x down. Both are written; trust the full-band one and
    # use the other to hear it clearly.
    uvc = undo_sinc5(uv, fs)
    for tag, x, note in (
            ("realtime", band_rms(uv, fs, AUDIBLE_LO, 50.0), f"{AUDIBLE_LO:g}-50 Hz"),
            ("realtime-corrected", band_rms(uvc, fs, AUDIBLE_LO, 50.0),
             f"{AUDIBLE_LO:g}-50 Hz, roll-off undone"),
            ("realtime-fullband", uv, "no band limit, ear filters it"),
            ("realtime-fullband-corrected", uvc,
             "no band limit, roll-off undone")):
        up = resample_poly(x, int(WAV_SR), int(fs))
        peak = float(np.max(np.abs(up)))
        up = (up / peak * 0.95 * 32767).astype(np.int16) if peak else up.astype(np.int16)
        out = os.path.join(OUT, f"audible-{label}-{tag}.wav")
        wavfile.write(out, WAV_SR, up)
        print(f"wrote {out}  ({len(up)/WAV_SR:.1f} s, 1:1 real time, {note}, "
              f"peak {peak:.0f} uV)")
    print("both need headphones or a woofer -- laptop speakers roll off near 150 Hz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", required=True, help="event origin, ISO Z")
    ap.add_argument("--pre", type=float, default=30.0, help="quiet seconds before origin")
    ap.add_argument("--post", type=float, default=45.0, help="seconds after origin")
    ap.add_argument("--label", default="event")
    ap.add_argument("--out", default=None)
    ap.add_argument("--wav", action="store_true",
                    help="also write a REAL-TIME (1:1) wav of what was audible")
    a = ap.parse_args()

    from obspy import UTCDateTime, read

    t0 = UTCDateTime(a.origin)
    day = os.path.join(DATA, f"SS.OAKM1.00.EHZ.D.{t0.year}.{t0.julday:03d}.mseed")
    if not os.path.exists(day):
        sys.exit(f"no day-file {day} -- pull it from pi5 first")

    st = read(day, starttime=t0 - a.pre - 5, endtime=t0 + a.post + 5)
    st.merge(method=1, fill_value="interpolate")        # day-files are ~10 s fragments
    tr = st[0]
    fs = tr.stats.sampling_rate
    uv = tr.data.astype(float) * UV_PER_COUNT
    uv -= uv.mean()
    sos = butter(2, HP_HZ / (fs / 2.0), btype="high", output="sos")
    uv = sosfiltfilt(sos, uv)
    t = np.arange(len(uv)) / fs + (tr.stats.starttime - t0)

    # Noise window: everything comfortably before the origin. Signal window: the first
    # 20 s after it, which covers P, S and the early coda at this distance.
    quiet = (t > -a.pre) & (t < -3.0)
    live = (t > 0.0) & (t < 20.0)

    uvc = undo_sinc5(uv, fs)

    print(f"{a.label}: fs={fs} Hz, Nyquist={fs/2:.0f} Hz, {len(uv)} samples")
    print(f"{'band':>14}  {'quiet uV':>9}  {'event uV':>9}  {'ratio':>6}  "
          f"{'event uV corr':>13}  {'boost':>6}")
    bands = [(1, 15), (15, 25), (25, 35), (35, 50), (AUDIBLE_LO, 50)]
    rows = []
    for lo, hi in bands:
        b, bc = band_rms(uv, fs, lo, hi), band_rms(uvc, fs, lo, hi)
        q, sg, sc = b[quiet].std(), b[live].std(), bc[live].std()
        rows.append((lo, hi, q, sg, sg / q if q else float("nan"), sc))
        tag = f"{lo:g}-{hi:g} Hz"
        print(f"{tag:>14}  {q:9.3f}  {sg:9.3f}  {sg/q if q else 0:5.1f}x  "
              f"{sc:13.3f}  {sc/sg if sg else 0:5.2f}x")

    # ---- figure ----
    fig, axes = plt.subplots(4, 1, figsize=(11, 13),
                             gridspec_kw=dict(height_ratios=[1.1, 2.2, 1.1, 1.6]))

    ax = axes[0]
    ax.plot(t, uv, lw=0.4, color="#222")
    ax.set_ylabel("uV")
    ax.set_title(f"{a.label} -- full band, {HP_HZ} Hz high-pass only")
    ax.set_xlim(t[0], t[-1])
    ax.grid(alpha=0.3)

    ax = axes[1]
    specgram.FMAX_HZ = fs / 2.0          # the whole point: show all of Nyquist
    mesh = specgram.draw(ax, uv, fs, t0=t[0])
    for hz in HVAC_HZ:
        ax.axhline(hz, color="#00d0ff", lw=0.6, alpha=0.55)
    ax.axhline(MAINS_ALIAS_HZ, color="#ff4d4d", lw=0.7, alpha=0.6, ls="--")
    ax.axhline(AUDIBLE_LO, color="w", lw=1.1, ls=":")
    ax.text(t[0] + 0.4, AUDIBLE_LO + 1.0, "20 Hz - audible above here",
            color="w", fontsize=8)
    ax.text(t[0] + 0.4, MAINS_ALIAS_HZ + 0.6, "HVAC lines (cyan) / 60 Hz alias (red)",
            color="w", fontsize=7)
    ax.set_ylabel("Hz")
    ax.set_title("spectrogram to the full 50 Hz Nyquist (standard plots crop at 25)")
    fig.colorbar(mesh, ax=ax, pad=0.01, label="dB re 1 uV^2/Hz")

    ax = axes[2]
    ax.plot(t, band_rms(uv, fs, AUDIBLE_LO, 50.0), lw=0.5, color="#b02020")
    ax.set_ylabel("uV")
    ax.set_xlabel("seconds after origin")
    ax.set_title(f"{AUDIBLE_LO:g}-50 Hz only -- the part that could be heard "
                 "(uncorrected for the ADC roll-off)")
    ax.set_xlim(t[0], t[-1])
    ax.grid(alpha=0.3)

    ax = axes[3]
    for win, lab, c in ((quiet, "before (noise)", "#888"), (live, "event", "#b02020")):
        f, p = welch(uv[win], fs=fs, nperseg=int(4 * fs))
        ax.semilogy(f, np.sqrt(p), color=c, lw=1.0, label=lab)
    f, p = welch(uvc[live], fs=fs, nperseg=int(4 * fs))
    ax.semilogy(f, np.sqrt(p), color="#e08000", lw=1.3,
                label="event, roll-off undone")
    fgrid = np.linspace(0.5, fs / 2, 400)
    ax.semilogy(fgrid, sinc5_response(fgrid, fs) * ax.get_ylim()[1] * 0.8,
                color="#2060c0", lw=1.2, ls="--",
                label="ADS1256 sinc^5 response (relative)")
    for hz in HVAC_HZ:
        ax.axvline(hz, color="#00a0c0", lw=0.6, alpha=0.5)
    ax.axvline(MAINS_ALIAS_HZ, color="#ff4d4d", lw=0.7, alpha=0.5, ls="--")
    ax.axvspan(AUDIBLE_LO, fs / 2, color="#ffcc00", alpha=0.10)
    ax.set_xlim(0, fs / 2)
    ax.set_xlabel("Hz")
    ax.set_ylabel("uV/sqrt(Hz)")
    ax.set_title("spectra: shaded = audible band. The dashed curve is what the ADC "
                 "takes OUT of it.")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which="both")

    fig.tight_layout()
    out = a.out or os.path.join(OUT, f"audible-{a.label}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"\nwrote {out}")

    if a.wav:
        write_wav(uv, fs, t, a.label)

    # The headline number, corrected for the filter that removed it.
    lo, hi, q, sg, r, sc = rows[-1]
    print(f"audible band {lo:g}-{hi:g} Hz: {r:.1f}x above the pre-event floor, "
          f"{sg:.1f} uV rms as archived and {sc:.1f} uV rms with the ADC roll-off "
          f"undone ({sc/sg:.2f}x). The ratio to the floor is unchanged by the "
          f"correction, as it must be.")


if __name__ == "__main__":
    main()
