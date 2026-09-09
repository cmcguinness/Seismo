#!/usr/bin/env python3
"""Serial monitor that does NOT reset the ESP32.

The board's auto-reset circuit is driven by DTR/RTS. Opening the port normally
asserts them and reboots it -- which destroyed the glitch-episode state every
single time we went to read it, and reset uptime to zero. Clearing them after
open() is too late; the pulse has already happened.

Two things are required:
  * set dtr/rts False BEFORE open()
  * clear HUPCL, or closing the port resets the board on the way out
"""
import sys, time, termios, serial

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-20120"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0

s = serial.Serial()
s.port = port
s.baudrate = 115200
s.timeout = 1
s.dtr = False          # must be set before open(), not after
s.rts = False
s.open()

# clear HUPCL so close() does not yank DTR and reboot the board
attrs = termios.tcgetattr(s.fd)
attrs[2] &= ~termios.HUPCL
termios.tcsetattr(s.fd, termios.TCSANOW, attrs)

t0 = time.time()
while time.time() - t0 < secs:
    line = s.readline()
    if line:
        sys.stdout.write(line.decode("utf8", "replace"))
        sys.stdout.flush()
