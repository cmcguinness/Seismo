"""creader.py — sample source backed by the C reader (station/adsreader/adsreader.c).

Same shape as rdatac.RdatacReader -- start(), read() -> (sample | None, dropped),
stop(), plus the counters the recorder puts in health.json -- but the samples come
from a subprocess that owns the ADS1256 outright and streams 16-byte records:

    u64 ts_ns   CLOCK_REALTIME ns of the DRDY edge, stamped by the kernel IRQ handler
    s32 sample  24-bit conversion
    u16 lost    conversions missed since the previous record (kernel line_seqno gap)
    u16 flags   nonzero = the read landed in the chip's update window / all-zero frame

What that buys over the pigpio path (STATUS.md 2026-08-25 "RECORDER"): every lost
conversion is COUNTED (the sampled-GPIO path lost ~0.2 % silently), and every kept one
carries a timestamp with no scheduling latency in it -- so the recorder can time blocks
from the data instead of steering a sample index to time.time().

The pipe between the two processes is the buffer the 10 ms deadline never had:
F_SETPIPE_SZ to 1 MB ≈ 17 min of samples at 100 sps. If Python stalls for a block
flush, the C side does not care.

`read()` returns (None, lost) for a flagged frame, exactly like RdatacReader's
register-update-window glitch, so the recorder's hold-last-good path is unchanged.
"""
import fcntl
import os
import struct
import subprocess
from pathlib import Path

REC = struct.Struct("<QiHH")
REC_SIZE = REC.size
PIPE_BYTES = 1 << 20
F_SETPIPE_SZ = getattr(fcntl, "F_SETPIPE_SZ", 1031)     # Linux; absent on macOS

DEFAULT_BIN = Path(__file__).resolve().parent / "adsreader" / "adsreader"


class CReader:
    def __init__(self, gain: int, drate_sps: int, binary: str | os.PathLike | None = None):
        self.gain = int(gain)
        self.sps = int(drate_sps)
        self.binary = Path(binary or os.environ.get("SEISMO_ADSREADER", DEFAULT_BIN))
        self.proc: subprocess.Popen | None = None
        self._fd = -1
        self._buf = b""
        self.total = 0
        self.dropped_total = 0        # conversions the C side reported lost
        self.glitches = 0             # flagged frames (value unreliable)
        self.last_ts: float | None = None     # epoch seconds of the last sample's DRDY edge
        self.last_ts_ns: int = 0

    def start(self) -> None:
        if not self.binary.exists():
            raise FileNotFoundError(f"adsreader binary not found: {self.binary} (run make in station/adsreader)")
        self.proc = subprocess.Popen(
            [str(self.binary), "--gain", str(self.gain), "--sps", str(self.sps)],
            stdout=subprocess.PIPE, stderr=None, bufsize=0)
        self._fd = self.proc.stdout.fileno()
        try:
            fcntl.fcntl(self._fd, F_SETPIPE_SZ, PIPE_BYTES)
        except OSError as e:                     # capped by /proc/sys/fs/pipe-max-size
            print(f"  creader: could not grow the pipe to {PIPE_BYTES} B ({e}); default 64 KB", flush=True)

    def read(self) -> tuple[int | None, int]:
        """Block until the next record. Returns (sample or None, lost)."""
        while len(self._buf) < REC_SIZE:
            chunk = os.read(self._fd, 4096)
            if not chunk:
                rc = self.proc.poll() if self.proc else None
                raise RuntimeError(f"adsreader stream ended (exit {rc})")
            self._buf += chunk
        ts_ns, sample, lost, flags = REC.unpack_from(self._buf)
        self._buf = self._buf[REC_SIZE:]
        self.total += 1
        self.dropped_total += lost
        self.last_ts_ns = ts_ns
        self.last_ts = ts_ns / 1e9
        if flags:
            self.glitches += 1
            return None, lost
        return sample, lost

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.terminate()                # C side leaves RDATAC + RESETs the chip
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
