"""specgram.py -- the project's STANDARD spectrogram, so every one we make is
directly comparable. Import and call `draw()`; don't hand-roll spectrograms
elsewhere. Deviate from these choices only with a documented reason.

  colormap    magma
  COLOR AXIS  -25 .. +25 dB   (10*log10 of PSD, (microvolt)^2/Hz, response-uncorrected)
  window      1.5 s STFT, 0.2 s hop   -> ~0.67 Hz freq resolution, +/-0.75 s time smear
  freq axis   0 .. 25 Hz   (below the 30 Hz Nyquist at 60 sps; revisit if fs changes)
  input       ground motion in microVOLTS, high-passed at 0.7 Hz (DC/tilt removed),
              FULL BAND (not the display bandpass) so content up to Nyquist is shown

The fixed color axis is the whole point: the same colour is the same absolute power
in every plot, so a real event and a non-detection sit on one ruler and can be laid
side by side. (Matplotlib's default auto-scaling would silently re-normalise each
plot to its own data, making brightness meaningless across figures.)
"""
import numpy as np
from scipy.signal import butter, sosfiltfilt, spectrogram

# --- the standard (change here, and every spectrogram changes together) ---
VMIN_DB, VMAX_DB = -25.0, 25.0
WINDOW_S = 1.5
HOP_S = 0.2
FMAX_HZ = 25.0
HP_HZ = 0.7
CMAP = "magma"


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
                         shading="gouraud", cmap=CMAP,
                         vmin=VMIN_DB, vmax=VMAX_DB, rasterized=True)
    ax.set_ylim(0, min(fs / 2.0, FMAX_HZ))
    return mesh
