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
