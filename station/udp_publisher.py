#!/usr/bin/env python3
"""udp_publisher.py -- fail-open UDP publisher for the seismic record stream.

The recorder's writer packs each miniSEED record and also hands the packed bytes
here via publish(). A daemon thread sends each record out a UDP datagram carrying
the last N records (sliding-window redundancy -- rev2-data-plane.md sec 5/14), PACED
to the record period so the N copies are spaced in time. Pacing matters because the
writer emits a whole 10 s block's worth of records at once; without it both copies
of a record would ride the same burst and the redundancy would buy nothing against a
short fade.

Datagram wire format (sec 14.1):  MAGIC 'SZ' | ver | n_records | seq(u32) | N x record

Fail-open by construction: publish() never blocks or raises (drop-on-full queue), and
a dead link is just UDP fire-and-forget -- the ADC/sampling loop is never touched.
Archive completeness is the pi5's job (seq-gap detect + backfill), not this path's.
"""
import datetime
import json
import queue
import socket
import struct
import threading
import time
from collections import deque

MAGIC = b"SZ"
VERSION = 1
HDR = struct.Struct("!2sBBI")   # magic, version, n_records, seq


class UdpPublisher:
    def __init__(self, host, port, n=2, record_period_s=1.0, maxq=256):
        self._addr = (host, int(port))
        self._n = max(1, int(n))
        self._period = float(record_period_s)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._q: queue.Queue = queue.Queue(maxsize=maxq)
        self._recent: deque = deque(maxlen=self._n)
        self._seq = 0
        self._dropped = 0
        self._sent = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, name="udp-publisher", daemon=True)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop.set()

    @property
    def stats(self):
        return {"udp_sent": self._sent, "udp_dropped": self._dropped}

    @property
    def seq(self):
        """Highest data-datagram seq sent so far (hi_seq for the heartbeat)."""
        return self._seq

    def publish(self, record_bytes):
        """Called from the writer thread. NEVER blocks or raises (fail-open)."""
        try:
            self._q.put_nowait(record_bytes)
        except queue.Full:
            self._dropped += 1   # link/pi5 behind -> drop; backfill recovers the archive

    def _run(self):
        next_send = time.monotonic()
        while not self._stop.is_set():
            try:
                rec = self._q.get(timeout=0.5)
            except queue.Empty:
                next_send = time.monotonic()      # idle: reset the pacing clock
                continue
            try:
                self._recent.append(rec)
                payload = b"".join(self._recent)
                hdr = HDR.pack(MAGIC, VERSION, len(self._recent), self._seq & 0xFFFFFFFF)
                self._sock.sendto(hdr + payload, self._addr)
                self._seq += 1
                self._sent += 1
            except Exception:
                pass                               # a dead socket must never kill the recorder
            # Pace to the record period so the N copies are spaced in time. If a whole
            # block just landed in the queue we're behind -> catch up without sleeping.
            next_send += self._period
            dt = next_send - time.monotonic()
            if dt > 0:
                self._stop.wait(dt)
            else:
                next_send = time.monotonic()       # too far behind: resync, don't spiral


class Heartbeat:
    """Station->pi5 liveness/health pulse (rev2-data-plane.md sec 6), on its OWN port,
    separate from the data stream -- its *absence* is the signal, so it fires on a fixed
    ~1 s cadence regardless of whether data is flowing.

    Payload (JSON): the current health counters plus `hi_seq` (highest data seq sent, so
    the pi5 can bound tail loss) and `hb_seq`/`t`. Best-effort fire-and-forget, no retry;
    `hi_seq` is cumulative so a lost heartbeat is re-reported by the next.
    """
    def __init__(self, host, port, get_state, period_s=1.0):
        self._addr = (host, int(port))
        self._get = get_state            # callable -> dict (health counters incl hi_seq)
        self._period = float(period_s)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._n = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, name="udp-heartbeat", daemon=True)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._n += 1
                payload = {"t": datetime.datetime.now(datetime.timezone.utc).isoformat(
                               timespec="milliseconds"),
                           "hb_seq": self._n}
                try:
                    payload.update(self._get() or {})
                except Exception:
                    pass                  # never let a bad state read stop the pulse
                self._sock.sendto(json.dumps(payload).encode(), self._addr)
            except Exception:
                pass                      # a dead socket must never kill the recorder
            self._stop.wait(self._period)
