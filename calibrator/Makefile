# Firmware for the inline calibration injector. See doc/BOM-calibrator.md.
#
#   brew install avrdude                     # homebrew-core, nothing special needed
#   brew tap osx-cross/avr
#   brew trust osx-cross/avr                 # <- REQUIRED, and it is a real decision
#   brew install avr-gcc
#
# Modern Homebrew refuses to load formulae from a third-party tap until you trust it,
# because a tap can run arbitrary code at install time: "Error: Refusing to load
# formula osx-cross/avr/avr-gcc@9 from untrusted tap". osx-cross/avr is the standard
# AVR tap and what every macOS AVR guide points at, but it is still third-party.
# If you would rather not grant that: `brew install arduino-cli` (which IS in
# homebrew-core) then `arduino-cli core install arduino:avr` gets you an avr-gcc from
# Arduino's own distribution, and you point CC at it.
#
# avrdude needs none of this -- it is in homebrew-core.
#
# Everything here is macOS-friendly; the Windows-only tone of most USBasp listings is
# about the vendor's GUI, not the hardware. avrdude speaks to it fine.

MCU     = attiny85
F_CPU   = 1000000UL
PROG    = usbasp
PART    = t85

# -B 8 slows the ISP clock to ~93 kHz. The chip ships with CKDIV8 set, so it runs at
# 1 MHz and SCK must stay below F_CPU/4 = 250 kHz. At the USBasp's default ~375 kHz
# the target simply does not answer, which reads as a wiring fault and is not one.
# This is the single most common way a first-time ATtiny session goes wrong.
SLOW    = -B 8

CFLAGS  = -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Os -Wall -Wextra -std=gnu99 \
          -ffunction-sections -fdata-sections -Wl,--gc-sections

all: calibrator.hex

calibrator.elf: calibrator.c hal.h bench.h
	avr-gcc $(CFLAGS) -o $@ $<
	avr-size $@

calibrator.hex: calibrator.elf
	avr-objcopy -O ihex -R .eeprom $< $@

flash: calibrator.hex
	avrdude -c $(PROG) -p $(PART) $(SLOW) -U flash:w:$<:i

# ---------------------------------------------------------------------------
# BENCH MULE -- an Elegoo Uno R3 (ATmega328P, 16 MHz) running the same calibrator.c.
#
# The tiny85 has no serial port and no spare pin to probe, so the burst timing and the
# button state machine are hard to observe on the thing that ships. The mule runs the
# identical source -- hal.h supplies the register and pin differences, bench.c adds a
# microsecond edge log on top -- and reports what it did over USB:
#
#   make mule-flash && make mule-watch     build, program, then watch it fire
#   screen $(MULE_PORT) 115200             same thing by hand; quit with C-a k
#
# Wiring: nothing. The injector is D11, the button is D12 (short it to GND with a
# jumper -- tap for a short press, hold 2 s for a long one), and the burst is visible
# on the onboard D13 LED.
#
# THE SCHEDULE IS COMPRESSED and nothing else is. TICKS_PER_HOUR=1 makes an "hour" one
# watchdog period, i.e. 8 s, so the 48 h soak takes 6.4 minutes and the 6 h period
# takes 48 s -- long enough to be a real test of nap()/nap_hours(), short enough to sit
# through. The PROTOCOL constants are untouched, so the pulse train the mule emits is
# bit-for-bit the one the flight board will emit. Override on the command line if you
# want to skip the soak while iterating:  make mule-flash MULE_SOAK_H=1
# ---------------------------------------------------------------------------
MULE_MCU        = atmega328p
MULE_F_CPU      = 16000000UL
MULE_PART       = m328p
MULE_PROG       = arduino
MULE_BAUD       = 115200
MULE_SOAK_H     = 48
MULE_PERIOD_H   = 6
MULE_TICKS_H    = 1

# The Uno enumerates as a usbmodem whose suffix is the USB location, so it changes if
# you move the cable to another port. Pick the one that answers rather than hard-coding
# it; override with `make mule-flash MULE_PORT=/dev/cu.usbmodemXXXX` if you have two.
MULE_PORT ?= $(shell ls /dev/cu.usbmodem* 2>/dev/null | head -1)

MULE_CFLAGS = -mmcu=$(MULE_MCU) -DF_CPU=$(MULE_F_CPU) -Os -Wall -Wextra -std=gnu99 \
              -ffunction-sections -fdata-sections -Wl,--gc-sections \
              -DSOAK_H=$(MULE_SOAK_H) -DPERIOD_H=$(MULE_PERIOD_H) \
              -DTICKS_PER_HOUR=$(MULE_TICKS_H)U

mule: mule.hex

# The compressed schedule arrives as -D flags, and make cannot see a flag change the
# way it sees a file change -- so `make mule-flash MULE_SOAK_H=1` would happily flash a
# stale hex built with the old numbers and leave you watching a board that is doing
# exactly what you told it to six minutes ago. Stamping the flags into a file makes
# them a dependency like anything else. (Ask how this comment came to be written.)
.mule-flags: FORCE
	@echo '$(MULE_CFLAGS)' | cmp -s - $@ || echo '$(MULE_CFLAGS)' > $@
FORCE:

mule.elf: calibrator.c bench.c hal.h bench.h .mule-flags
	avr-gcc $(MULE_CFLAGS) -o $@ calibrator.c bench.c
	avr-size $@

mule.hex: mule.elf
	avr-objcopy -O ihex -R .eeprom $< $@

mule-flash: mule.hex
	@test -n "$(MULE_PORT)" || { echo "no /dev/cu.usbmodem* -- is the Uno plugged in?"; exit 1; }
	avrdude -c $(MULE_PROG) -p $(MULE_PART) -P $(MULE_PORT) -b $(MULE_BAUD) -U flash:w:$<:i

# Opening the port resets the board (DTR), so this always catches it from power-up --
# which is what you want, since the state machine starts in the soak.
mule-watch:
	@test -n "$(MULE_PORT)" || { echo "no /dev/cu.usbmodem* -- is the Uno plugged in?"; exit 1; }
	@echo "watching $(MULE_PORT) at $(MULE_BAUD) -- ^C to stop"
	@python3 -c "import serial,sys; p=serial.Serial('$(MULE_PORT)',$(MULE_BAUD)); \
	  [sys.stdout.write(p.readline().decode('ascii','replace')) or sys.stdout.flush() for _ in iter(int,1)]" \
	  2>/dev/null || screen $(MULE_PORT) $(MULE_BAUD)

# The factory defaults are already what this design wants, so the normal answer here
# is to READ them and change nothing:
#   lfuse 0x62  internal 8 MHz RC with CKDIV8 -> 1 MHz. Slow is the point.
#   hfuse 0xDF  BOD DISABLED, SPIEN enabled, RSTDISBL not set.
#   efuse 0xFF
# BOD matters: brown-out detection costs ~20 uA continuously, which is several times
# the whole sleeping budget and would turn years of battery life into months. There is
# nothing for it to protect -- a coin cell sags gently and the worst case is a burst
# that does not fire.
# NEVER set RSTDISBL. It buys one more GPIO and costs you the ability to program the
# chip again with anything short of a high-voltage programmer.
fuses:
	avrdude -c $(PROG) -p $(PART) $(SLOW) -U lfuse:r:-:h -U hfuse:r:-:h -U efuse:r:-:h

writefuses:
	avrdude -c $(PROG) -p $(PART) $(SLOW) \
	  -U lfuse:w:0x62:m -U hfuse:w:0xDF:m -U efuse:w:0xFF:m

clean:
	rm -f calibrator.elf calibrator.hex mule.elf mule.hex .mule-flags

.PHONY: all flash fuses writefuses clean mule mule-flash mule-watch FORCE
