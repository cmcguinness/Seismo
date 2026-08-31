# Firmware for the inline calibration injector. See doc/BOM-calibrator.md.
#
#   brew tap osx-cross/avr && brew install avr-gcc
#   brew install avrdude
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

calibrator.elf: calibrator.c
	avr-gcc $(CFLAGS) -o $@ $<
	avr-size $@

calibrator.hex: calibrator.elf
	avr-objcopy -O ihex -R .eeprom $< $@

flash: calibrator.hex
	avrdude -c $(PROG) -p $(PART) $(SLOW) -U flash:w:$<:i

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
	rm -f calibrator.elf calibrator.hex

.PHONY: all flash fuses writefuses clean
