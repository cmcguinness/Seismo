#!/usr/bin/env python3
"""recorder.py — continuous seismic recorder: geophone -> rolling miniSEED.

Reads the differential geophone channel and writes miniSEED day-files to
DATA_DIR, ready for a helicorder / ObsPy / SeisComP. Uses simplemseed (pure
Python, numpy-only) rather than ObsPy: this is a lean 24/7 ACQUISITION daemon
on a 1 GB Pi 2B, and ObsPy's scipy/matplotlib weight belongs on the analysis
side (run that on the Mac against the files this produces).

RAW ADC counts are stored (miniSEED convention); volts-per-count and the
geophone response live in station metadata, applied at analysis time.

Format details (learned the hard way):
  - int32 encoding (code 3), uncompressed. ~19 MB/day at 56 sps -- fine on the
    9 GB free here; STEIM2 compression is a later optimisation.
  - 512-byte records hold ~114 int32 samples, so each block is chunked into
    100-sample records.
  - miniSEED2 stores rate as integer factor x mult, and simplemseed's auto-calc
    is broken -> we pass sampRateFactor/sampRateMult explicitly (integer rate).

Timing: the read path can't hold the DRATE nominal exactly (per-sample SYNC,
~55-57 sps, mildly load-dependent). We declare a FIXED rate (SEISMO_RATE), NOT
the per-run measured value -- otherwise restarts land on different integers and
ObsPy refuses to merge a day-file with mixed rates. Each block is re-anchored to
the wall clock (NTP-kept UTC), which absorbs the small real-vs-declared wander
as a sub-block overlap that never accumulates. We still measure the true rate at
startup, only to log it. (A crystal-exact, drift-free rate needs RDATAC mode.)

Config via environment (all optional):
  SEISMO_STATION/NETWORK/LOCATION/CHANNEL   SEED id   default XX.OAKMT.00.SHZ
  SEISMO_GAIN     PGA gain                  default 64
  SEISMO_DRATE    ADS1256 data rate (sps)   default 60
  SEISMO_RATE     declared miniSEED rate    default 57  (fixed -> single-rate archive)
  SEISMO_DATADIR  output directory          default ~/seismo/data
  SEISMO_BLOCK    seconds per flush         default 10

Ctrl-C / SIGTERM flushes the partial block and releases the ADC cleanly.
"""
import datetime
import json
import os
import queue
import signal
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
from simplemseed import MiniseedHeader, MiniseedRecord

from adc_common import DIFF, measure_rate, open_ads
from stalta import StaLta

STATION = os.environ.get("SEISMO_STATION", "OAKMT")
NETWORK = os.environ.get("SEISMO_NETWORK", "XX")   # XX = FDSN test/unregistered code.
                                                   # NOT "AM" -- that's Raspberry Shake's
                                                   # registered network; we're independent.
LOCATION = os.environ.get("SEISMO_LOCATION", "00")
CHANNEL = os.environ.get("SEISMO_CHANNEL", "SHZ")
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))
DRATE = int(os.environ.get("SEISMO_DRATE", "60"))
# RDATAC: free-running continuous read (station/rdatac.py). The ADC then samples on
# its own crystal at exactly DRATE instead of the legacy per-sample SYNC path's
# load-dependent 54-57 sps, and block boundaries stop carrying a ~68 ms gap.
# Declared rate becomes DRATE, so files are NOT mergeable with the 57 sps archive:
# enabling this starts a new configuration epoch.
RDATAC = os.environ.get("SEISMO_RDATAC", "0") == "1"
RATE = int(os.environ.get("SEISMO_RATE", str(DRATE) if RDATAC else "57"))
# ^ FIXED declared miniSEED rate: keeps the archive single-rate (mergeable) across
#   restarts. Legacy path re-measures to 55-57 so it must declare a constant; the
#   RDATAC path genuinely achieves DRATE, so it declares that.
DATADIR = Path(os.environ.get("SEISMO_DATADIR", str(Path.home() / "seismo" / "data")))
BLOCK_S = int(os.environ.get("SEISMO_BLOCK", "10"))
# Warm-up discarded after ADC init. The ADS1256 emits garbage for the first
# conversions following a pin reset -- measured as a ~97,800-count step (66x the
# ambient max) on 2026-07-24, once per restart. Unfiltered it trips the STA/LTA
# and, because heli_render clips excursions at +/-3 rows by design, a single such
# sample paints a solid six-row block across the drum. Read and throw away this
# many seconds before the block loop starts.
SETTLE_S = float(os.environ.get("SEISMO_SETTLE", "2.0"))

# STA/LTA event detector (see stalta.py). Runs inline; only writes on a trigger.
TRIG = float(os.environ.get("SEISMO_TRIG", "4.0"))     # STA/LTA on-threshold
DETRIG = float(os.environ.get("SEISMO_DETRIG", "1.5"))  # off-threshold
STA_S = float(os.environ.get("SEISMO_STA", "1.0"))
LTA_S = float(os.environ.get("SEISMO_LTA", "30.0"))
HP_HZ = float(os.environ.get("SEISMO_HP", "3.0"))       # high-pass corner; 3 Hz rejects sub-Hz tilt/settling (geophone deaf below 4.5 Hz) that a gentle 1-pole 1 Hz HPF let mistrigger
EVENTS_LOG = DATADIR.parent / "events.log"              # permanent JSONL record
EVENTS_LIVE = Path("/dev/shm/seismo_events.json")       # last N events, for the viewer
# Data-quality sidecar. A held/substituted sample is otherwise indistinguishable from
# real data downstream, which is exactly the mistake SEED's data-quality flags exist to
# prevent (bit 2 spikes, bit 3 glitches). Until we can set those flags in the records
# themselves, log every intervention with its UTC time so analysis can exclude them.
QC_LOG = DATADIR.parent / "qc.log"
HEALTH = DATADIR.parent / "health.json"                 # rsync'd; for the dashboard

SPR = 100                        # samples per 512-byte int32 record (<=114 fits)
ENC_INT32 = 3

# Live feed for real-time viewing (live_server.py): the sampling loop mirrors a
# rolling window of raw counts to a RAM-backed file. No ADC contention -- the
# viewer reads this file, never the chip.
LIVE_PATH = Path("/dev/shm/seismo_live.npz")
LIVE_SECONDS = 30                # width of the live waveform window
LIVE_PERIOD = 0.3                # how often to republish the ring (s)

_stop = threading.Event()
_q: queue.Queue = queue.Queue(maxsize=64)


def live_publisher(ring: deque, fs: float) -> None:
    """Every LIVE_PERIOD, snapshot the ring and atomically write it to shared
    memory for live_server.py. Runs in its OWN thread so the file I/O never
    delays the sampling loop. ring.copy() is a single C-level op (atomic vs the
    sampling thread's append); any transient error just skips one frame.

    t_end is the UTC epoch of the NEWEST sample in the snapshot -- stamped here
    because only the station knows it (the pi5 mirror's file mtime is its own
    copy time). The viewer needs it to label the time axis."""
    tmp = f"{LIVE_PATH}.tmp"
    while not _stop.is_set():
        time.sleep(LIVE_PERIOD)
        try:
            counts = np.array(ring.copy(), dtype=np.int32)
            t_end = time.time()
            if counts.size:
                with open(tmp, "wb") as f:
                    np.savez(f, counts=counts, fs=np.float64(fs), gain=np.int32(GAIN),
                             t_end=np.float64(t_end))
                os.replace(tmp, LIVE_PATH)
        except Exception:
            pass


def _emit_event(ev: dict) -> None:
    """Record a detected event: journal line + permanent JSONL + a rolling
    recent-events file for the viewer. Best-effort; never crashes the loop."""
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(seconds=ev["duration_s"])
    rec = {"start": start.isoformat(timespec="seconds"),
           "end": end.isoformat(timespec="seconds"), **ev}
    print(f"EVENT {start:%H:%M:%S}Z  dur {ev['duration_s']}s  "
          f"ratio {ev['peak_ratio']}  peak {ev['peak_uv']} uV", flush=True)
    try:
        with open(EVENTS_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
        recent = []
        if EVENTS_LIVE.exists():
            recent = json.loads(EVENTS_LIVE.read_text())
        recent = (recent + [rec])[-20:]
        tmp = f"{EVENTS_LIVE}.tmp"
        Path(tmp).write_text(json.dumps(recent))
        os.replace(tmp, EVENTS_LIVE)
    except Exception:
        pass


def _qc(kind: str, when: float, detail: dict | None = None) -> None:
    """Append one data-quality intervention to QC_LOG. Best-effort, never raises."""
    try:
        rec = {"t": datetime.datetime.fromtimestamp(
                   when, datetime.timezone.utc).isoformat(timespec="milliseconds"),
               "kind": kind}
        if detail:
            rec.update(detail)
        with open(QC_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _health(**kw) -> None:
    """Atomically publish acquisition counters for the dashboard."""
    try:
        kw["t"] = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds")
        tmp = f"{HEALTH}.tmp"
        Path(tmp).write_text(json.dumps(kw))
        os.replace(tmp, HEALTH)
    except Exception:
        pass


def _write_records(fh, samples, start, rate):
    """Chunk one block into 100-sample int32 records, appending to fh."""
    for i in range(0, len(samples), SPR):
        chunk = np.asarray(samples[i:i + SPR], dtype=np.int32)
        t = start + datetime.timedelta(seconds=i / rate)
        hdr = MiniseedHeader(NETWORK, STATION, LOCATION, CHANNEL, t, len(chunk),
                             rate, encoding=ENC_INT32,
                             sampRateFactor=rate, sampRateMult=1)
        fh.write(MiniseedRecord(hdr, chunk).pack())


def writer(rate: int) -> None:
    """Consume (samples, starttime) blocks and append to UTC day-files."""
    while True:
        item = _q.get()
        if item is None:
            break
        samples, start = item
        fn = (f"{NETWORK}.{STATION}.{LOCATION}.{CHANNEL}.D."
              f"{start.year}.{start.timetuple().tm_yday:03d}.mseed")
        with open(DATADIR / fn, "ab") as fh:      # append -> growing day-file
            _write_records(fh, samples, start, rate)


def main() -> None:
    DATADIR.mkdir(parents=True, exist_ok=True)

    def stop(*_):
        _stop.set()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    ads = open_ads(GAIN, DRATE)
    wt = None
    reader = None
    try:
        if RDATAC:
            from rdatac import ClockAnchor, Despiker, RdatacReader
            reader = RdatacReader(ads, DIFF)
            reader.start()
            fs = float(DRATE)                     # crystal-exact; no need to measure
            # Discard the post-reset garbage BEFORE anchoring the clock or writing
            # anything -- see SETTLE_S. Must come after start() (RDATAC has to be
            # streaming to read at all) and before the block loop.
            n_settle = int(fs * SETTLE_S)
            if n_settle:
                print(f"  warm-up: discarding {n_settle} samples ({SETTLE_S:g}s) after ADC reset")
                for _ in range(n_settle):
                    reader.read()
        else:
            fs = measure_rate(ads)                # measured actual rate (also primes read)
        rate = RATE                               # FIXED declared rate -> single-rate archive
        block_n = rate * BLOCK_S
        wt = threading.Thread(target=writer, args=(rate,), daemon=True)
        wt.start()
        mode = "RDATAC continuous" if RDATAC else "legacy per-sample SYNC"
        print(f"recording {NETWORK}.{STATION}.{LOCATION}.{CHANNEL}  "
              f"declared {rate} sps (measured {fs:.2f}), gain {GAIN}  [{mode}]")
        print(f"  -> {DATADIR}  ({BLOCK_S}s blocks, {block_n} samples each)")
        uv_per_count = 2.5 * 2 / (GAIN * (2 ** 23 - 1)) * 1e6
        detector = StaLta(fs, hp_hz=HP_HZ, sta_s=STA_S, lta_s=LTA_S,
                          trig=TRIG, detrig=DETRIG, uv_per_count=uv_per_count)
        print(f"  detector: STA/LTA trig {TRIG} (STA {STA_S}s / LTA {LTA_S}s, HP {HP_HZ}Hz)")
        print("Ctrl-C to stop.")

        buf = [0]
        block: list[int] = []
        live_ring: deque = deque(maxlen=int(fs * LIVE_SECONDS))
        threading.Thread(target=live_publisher, args=(live_ring, fs), daemon=True).start()
        nblocks = 0

        def utc(epoch: float) -> datetime.datetime:
            return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)

        if RDATAC:
            # Sample index is the timebase: ClockAnchor maps index -> UTC, steered
            # slowly to NTP (see rdatac.py). Block starts come from that prediction
            # rather than a fresh time.time() per block, so the read loop's
            # scheduling latency never lands in a block boundary.
            anchor = ClockAnchor(rate)
            n_total = 0
            block_n0 = 0
            last_good = 0
            glitch_in_block = False
            despiker = Despiker()
            while not _stop.is_set():
                sample, dropped = reader.read()
                if anchor.t0 is None:
                    # Anchor on the FIRST SAMPLE, not before the read loop: the
                    # pre-loop timestamp misses RDATAC entry plus up to one DRDY
                    # period, and that offset shows up as gaps at every early block
                    # boundary while the loop slews it out.
                    anchor.anchor(0, time.time())
                if dropped:
                    # The ADC produced samples we failed to collect; their VALUES are
                    # gone, so advance the index (keeps index->time honest) and cut
                    # the block. The file then shows a real gap instead of silently
                    # time-shifting everything after it.
                    # Cut the block (those sample VALUES are gone) and advance the
                    # index by the number lost -- which keeps index->time correct on
                    # its own, so do NOT re-anchor. Re-anchoring here turned a single
                    # dropped sample (16.7 ms) into a 71.5 ms gap by adding the
                    # measurement latency on top of the real loss.
                    print(f"  WARNING dropped {dropped} sample(s) -- cutting block",
                          flush=True)
                    _qc("dropped", time.time(), {"n": int(dropped)})
                    if block:
                        _q.put((block, utc(anchor.predict(block_n0))))
                        block = []
                    n_total += dropped
                    block_n0 = n_total
                if sample is None:
                    glitch_in_block = True
                    # Register-update collision: the frame clocked out zeros (see
                    # rdatac.read). Hold the previous value rather than write a
                    # 200 uV needle that trips the detector and speckles the drum.
                    # Timing is untouched -- the sample slot is real, only its value
                    # is unknown -- so this stays gapless. One held sample per ~100 s
                    # is a far smaller lie than a fabricated impulse.
                    sample = last_good
                    _qc("zero_frame", time.time(), {"held": int(last_good)})
                else:
                    last_good = sample
                # Despike BEFORE the detector: an isolated garbage frame read as a
                # 72 mV event and tripped the STA/LTA (13:53:55 UTC 2026-07-23).
                spikes_before = despiker.spikes
                sample = despiker.push(sample)
                if despiker.spikes != spikes_before:
                    _qc("spike", time.time(), {"held": int(sample)})
                if sample is None:
                    continue                     # first sample only: still buffering
                block.append(sample)
                live_ring.append(sample)
                n_total += 1
                try:                             # STA/LTA -- never break acquisition
                    ev = detector.update(sample)
                    if ev:
                        _emit_event(ev)
                except Exception:
                    pass
                if len(block) >= block_n:
                    # A glitch means the loop stalled, so this boundary's wall-clock
                    # reading is late by the stall (observed +16.7 ms, ~one sample
                    # period). Feeding that to the anchor would slew a fake error
                    # into the NEXT boundary as a small gap, so skip the update and
                    # coast on the existing prediction for one block.
                    err = 0.0 if glitch_in_block else anchor.update(n_total, time.time())
                    glitch_in_block = False
                    _q.put((block, utc(anchor.predict(block_n0))))
                    nblocks += 1
                    block = []
                    block_n0 = n_total
                    _health(mode="rdatac", rate=rate, blocks=nblocks,
                            rate_est=round(anchor.rate_est, 4),
                            clock_err_ms=round(err * 1000, 2),
                            dropped=reader.dropped_total, glitches=reader.glitches,
                            spikes=despiker.spikes, stalls=anchor.outliers,
                            resyncs=anchor.resyncs)
                    if nblocks % 6 == 0:          # ~once/min at 10s blocks
                        print(f"  {nblocks} blocks, clock err {err*1000:+.2f} ms, "
                              f"rate_est {anchor.rate_est:.4f} sps, "
                              f"dropped {reader.dropped_total}, "
                              f"glitches {reader.glitches}, spikes {despiker.spikes}, "
                              f"stalls {anchor.outliers}, "
                              f"resyncs {anchor.resyncs}",
                              flush=True)
            tail = despiker.flush()               # release the buffered sample
            if tail is not None:
                block.append(tail)
            if block:                             # flush partial block on stop
                _q.put((block, utc(anchor.predict(block_n0))))
        else:
            start = datetime.datetime.now(datetime.timezone.utc)
            while not _stop.is_set():
                sample = ads.read_continue([DIFF], buf)[0]
                block.append(sample)
                live_ring.append(sample)         # cheap; publisher thread does the I/O
                try:                             # STA/LTA detector -- never break acquisition
                    ev = detector.update(sample)
                    if ev:
                        _emit_event(ev)
                except Exception:
                    pass
                if len(block) >= block_n:
                    _q.put((block, start))
                    nblocks += 1
                    block = []
                    start = datetime.datetime.now(datetime.timezone.utc)
                    _health(mode="legacy", rate=rate, blocks=nblocks, measured=round(fs, 3))
                    if nblocks % 6 == 0:          # ~once/min at 10s blocks
                        print(f"  {nblocks} blocks written", flush=True)
            if block:                             # flush partial block on stop
                _q.put((block, start))
    finally:
        if reader is not None:
            reader.stop()                          # leave RDATAC before closing SPI
        if wt is not None:
            _q.put(None)                           # sentinel -> writer drains + exits
            wt.join(timeout=5)
        ads.stop_close_all()
        print(f"\nstopped. wrote to {DATADIR}")


if __name__ == "__main__":
    main()
