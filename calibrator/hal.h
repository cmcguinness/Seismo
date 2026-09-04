/* hal.h -- the small set of things that differ between the flight target and the
 * bench mule, so that calibrator.c is ONE source file built for both.
 *
 * The flight target is an ATtiny85 on a coin cell (doc/BOM-calibrator.md). The mule
 * is an Elegoo Uno R3 -- an ATmega328P at 16 MHz with a USB serial port and a header
 * you can clip a probe to, neither of which the tiny has. The point of the mule is to
 * develop and observe the burst timing and the button state machine on the bench; the
 * point of THIS file is that the mule runs the same logic while doing it. A mule with
 * its own reimplementation of burst() would prove nothing about the firmware that
 * actually ships.
 *
 * So the rule for what belongs here: register names and pin numbers, and nothing that
 * changes what the firmware DOES. If you find yourself wanting to put behaviour behind
 * one of these ifdefs, that is the signal that the mule has stopped being a mule.
 *
 * The two parts agree more than they differ, which is why this works at all: both are
 * AVR8, both name the wake vectors WDT_vect and PCINT0_vect, both have a PORTB with
 * the three pins we need on it, and the watchdog's timed-sequence dance is the same.
 */
#ifndef CALIBRATOR_HAL_H
#define CALIBRATOR_HAL_H

#if defined(__AVR_ATtiny85__)

/* ---------------- flight: ATtiny85, 1 MHz internal RC ---------------- */
#ifndef F_CPU
#define F_CPU 1000000UL
#endif

/* PB0/PB1/PB2 are MOSI/MISO/SCK and belong to the ISP header, so the injector and the
 * button take PB3 and PB4 and the LED has to share one of the programming pins. It
 * goes on MISO, not MOSI: MISO is driven by the ATTINY and merely read by the
 * programmer, so the extra few mA come out of a driver we control. On MOSI the load
 * would hang off the PROGRAMMER's output instead. PB5 is RESET and is left alone --
 * see the fuse note in doc/BOM-calibrator.md about never setting RSTDISBL. */
#define PIN_INJ     PB3
#define PIN_BTN     PB4     /* panel button, to ground, internal pull-up */
#define PIN_LED     PB1

/* Unused inputs get pull-ups so nothing floats and oscillates, which would cost more
 * standby current than the sleeping CPU does. */
#define PIN_IDLE_PULLUPS  ((1 << PB0) | (1 << PB2))

#define WDT_CTRL    WDTCR

/* Every peripheral off. PRR is the whole story on the tiny -- there is no
 * power_all_off() for this part. */
#define PRR_SETUP() (PRR = (1 << PRTIM1) | (1 << PRTIM0) | (1 << PRUSI) | (1 << PRADC))

#define PCINT_ENABLE()  do {            \
        GIMSK |= (1 << PCIE);           \
        PCMSK |= (1 << PIN_BTN);        \
    } while (0)

/* On the tiny, PB5 is RESET; putting the button there would cost the ability to
 * program the chip. On the mega it is just an ordinary pin (and the Uno's onboard
 * LED), so the assert is target-specific. */
#define ASSERT_BTN_NOT_RESET() \
        _Static_assert(PIN_BTN != PB5, "PB5 is RESET -- see the RSTDISBL note in the BOM")

#elif defined(__AVR_ATmega328P__)

/* ---------------- bench mule: ATmega328P, 16 MHz crystal ---------------- */
#ifndef F_CPU
#define F_CPU 16000000UL
#endif

/* Uno silkscreen: PB3 = D11, PB4 = D12, PB5 = D13. D13 is the onboard LED, which the
 * flight board's LED cannot be because PB5 is RESET on the tiny -- so on the mule the
 * burst is visible with no LED soldered to anything. D11 is the injector: that is the
 * pin to put a probe on, and the one bench.c watches. */
#define PIN_INJ     PB3
#define PIN_BTN     PB4     /* button to ground, internal pull-up -- or a jumper to GND */
#define PIN_LED     PB5     /* onboard */

/* PB0 is ICP1, left free for the input-capture upgrade noted in bench.c. */
#define PIN_IDLE_PULLUPS  ((1 << PB2))

#define WDT_CTRL    WDTCSR

/* Timer1 and the USART stay powered: they are the instrument. Everything else off,
 * for symmetry with flight rather than because a USB-powered board cares. */
#define PRR_SETUP() (PRR = (1 << PRTWI) | (1 << PRTIM2) | (1 << PRTIM0) \
                         | (1 << PRSPI) | (1 << PRADC))

#define PCINT_ENABLE()  do {            \
        PCICR |= (1 << PCIE0);          \
        PCMSK0 |= (1 << PIN_BTN);       \
    } while (0)

#define ASSERT_BTN_NOT_RESET()  /* PB5 is a normal pin here */

#define CALIBRATOR_MULE 1

#else
#error "calibrator.c targets the ATtiny85 (flight) or the ATmega328P (bench mule)"
#endif

#endif /* CALIBRATOR_HAL_H */
