"""specgram.py -- the project's STANDARD spectrogram, so every one we make is
directly comparable. Import and call `draw()`; don't hand-roll spectrograms
elsewhere. Deviate from these choices only with a documented reason.

  colormap    magma
  COLOR AXIS  -25 .. +25 dB on the lower 70% of the colormap, +25 .. +70 dB on the rest
              (10*log10 of PSD, (microvolt)^2/Hz, response-uncorrected; see TOP_DB)
  window      1.5 s STFT, 0.2 s hop   -> ~0.67 Hz freq resolution, +/-0.75 s time smear
  freq axis   0 .. 25 Hz   (below the 30 Hz Nyquist at 60 sps; revisit if fs changes)
  input       ground motion in microVOLTS, high-passed at 0.7 Hz (DC/tilt removed),
              FULL BAND (not the display bandpass) so content up to Nyquist is shown

The fixed color axis is the whole point: the same colour is the same absolute power
in every plot, so a real event and a non-detection sit on one ruler and can be laid
side by side. (Matplotlib's default auto-scaling would silently re-normalise each
plot to its own data, making brightness meaningless across figures.)
"""
import os

import numpy as np
from matplotlib.colors import Normalize
from scipy.signal import butter, sosfiltfilt, spectrogram

# --- the standard (change here, and every spectrogram changes together) ---
VMIN_DB = float(os.environ.get("SEISMO_SPEC_VMIN_DB", "-25"))
VMAX_DB = float(os.environ.get("SEISMO_SPEC_VMAX_DB", "25"))
# HEADROOM above VMAX_DB (2026-09-03). The -25..+25 dB axis saturated on every event
# bigger than about M2 at 40 km: the M3.5 under Larkfield-Wikiup peaked near +65 dB and
# drew as a solid yellow block for ten seconds, so nothing of the P-to-S-to-coda
# evolution could be seen until it was nearly over. Raising VMAX to 65 fixes that and
# ruins the small events, which then live in the bottom third of the colormap. So the
# axis is PIECEWISE: -25..+25 dB still occupies the lower KNEE_FRAC of the colormap (the
# same colours as before, slightly compressed), and +25..TOP_DB occupies the rest. The
# same colour is still the same absolute power in every plot, which was the whole point.
TOP_DB = float(os.environ.get("SEISMO_SPEC_TOP_DB", "70"))
KNEE_FRAC = float(os.environ.get("SEISMO_SPEC_KNEE_FRAC", "0.7"))
WINDOW_S = 1.5
HOP_S = 0.2
FMAX_HZ = 25.0
HP_HZ = 0.7
CMAP = "magma"


class _PiecewiseDb(Normalize):
    """VMIN..VMAX -> 0..KNEE_FRAC, VMAX..TOP -> KNEE_FRAC..1. Fixed, so comparable."""
    def __call__(self, value, clip=None):
        v = np.ma.asarray(value, dtype=float)
        knots_x = [VMIN_DB, VMAX_DB, TOP_DB]
        knots_y = [0.0, KNEE_FRAC, 1.0]
        return np.ma.masked_array(np.interp(v, knots_x, knots_y), mask=np.ma.getmask(v))

    def inverse(self, value):
        return np.interp(value, [0.0, KNEE_FRAC, 1.0], [VMIN_DB, VMAX_DB, TOP_DB])


def _norm():
    if TOP_DB <= VMAX_DB:
        return Normalize(vmin=VMIN_DB, vmax=VMAX_DB)
    return _PiecewiseDb(vmin=VMIN_DB, vmax=TOP_DB)


def draw(ax, uv, fs, t0=0.0):
    """Render the standard spectrogram of raw ground-motion `uv` (microvolts) at
    sample rate `fs` onto `ax`. `t0` is the time of the first sample (sets the
    x-axis origin). Returns the QuadMesh (for an optional colorbar)."""
    x = np.asarray(uv, dtype=float)
    x = x - np.mean(x)
    sos = butter(2, HP_HZ / (fs / 2.0), btype="high", output="sos")
    x = sosfiltfilt(sos, x)
    npg = max(16, int(WINDOW_S * fs))
    nov = npg - max(1, int(HOP_S * fs))
    f, tt, sxx = spectrogram(x, fs=fs, nperseg=npg, noverlap=nov)
    mesh = ax.pcolormesh(tt + t0, f, 10.0 * np.log10(sxx + 1e-6),
                         shading="gouraud", cmap=CMAP, norm=_norm(), rasterized=True)
    ax.set_ylim(0, min(fs / 2.0, FMAX_HZ))
    return mesh
