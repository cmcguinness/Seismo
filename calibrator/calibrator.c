/* calibrator.c -- inline geophone calibration injector, ATtiny85.
 *
 * Closes a PhotoMOS three times into the geophone coil, four times a day, forever,
 * on a single CR2032. The station is recording normally throughout, so each burst
 * lands in the archive as an ordinary transient; analysis/calfinder.py finds it again
 * by its signature and hands the release instants to analysis/ringdown.py, which fits
 * f0 and zeta. Nothing here knows or cares about any of that -- it just has to fire a
 * recognisable pattern and then get out of the way for six hours.
 *
 * THE PROTOCOL BLOCK BELOW IS SHARED WITH analysis/calfinder.py. The two files are
 * halves of one agreement: the firmware emits the signature, the finder recognises
 * it. calfinder.py's self-test parses this file and fails if the numbers drift apart,
 * so change them in one place and the other will tell you.
 *
 * WHY A MICRO AND NOT A 555. The three-pulses-at-a-fixed-spacing pattern is what makes
 * a burst self-identifying in a day of seismic data; that is trivial in firmware and
 * clumsy in logic, and a CMOS 555's ~150 uA quiescent would flatten a coin cell in
 * months where this draws ~5 uA and lasts years.
 *
 * TIMEKEEPING IS DELIBERATELY BAD. The watchdog runs off an uncalibrated RC oscillator
 * that drifts with temperature and supply, so "four times a day" will wander, and the
 * 2.00 s spacing is really 2.0 s +/- a few percent. That is fine and by design: the
 * burst is identified by SHAPE, not by when it arrives, and calfinder.py measures the
 * spacing rather than assuming it. Do not add a crystal to fix a problem we do not
 * have -- it would cost parts, board space and standby current for nothing.
 *
 *   make            build
 *   make flash      program via USBasp
 *   make fuses      READ the fuses and check them (factory defaults are correct)
 */
#define F_CPU 1000000UL

#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <avr/wdt.h>
#include <util/delay.h>

/* ---- PROTOCOL: keep in step with analysis/calfinder.py ---- */
#define N_PULSES    3       /* two is a coincidence, four costs charge for nothing */
#define PULSE_MS    500     /* many decay time-constants, so the step-on has died
                             * before the step-off releases */
#define SPACING_MS  2000    /* leaves >= 1.5 s of quiet after each release to fit in */

/* ---- schedule ---- */
#define SOAK_H      48      /* silence after power-up. Two full diurnal cycles of
                             * "off" before the first burst, so the archive holds a
                             * clean before-picture to compare every later burst
                             * against. Enforced here rather than by remembering not
                             * to install it yet. */
#define PERIOD_H    6       /* four bursts a day */

/* The button is two commands, told apart by how long it is held. A SHORT press
 * RESTARTS the soak; a LONG press fires a burst immediately.
 *
 * That asymmetry is deliberate and it is the safe way round. This box sits on a shelf
 * for months, so the realistic button event is an accidental knock -- and the harmless
 * response to an accident is to start the quiet period again, not to skip it. Firing
 * the injector is the deliberate act, so it is the one that has to be held for. */
#define LONG_PRESS_MS  2000

/* ---- pins ----
 * PB0/PB1/PB2 are MOSI/MISO/SCK and belong to the ISP header, so the injector and the
 * button take PB3 and PB4 and the LED has to share one of the programming pins. It
 * goes on MISO, not MOSI: MISO is driven by the ATTINY and merely read by the
 * programmer, so the extra few mA come out of a driver we control. On MOSI the load
 * would hang off the PROGRAMMER's output instead. PB5 is RESET and is left alone --
 * see the fuse note in doc/BOM-calibrator.md about never setting RSTDISBL.
 */
#define PIN_INJ     PB3
#define PIN_BTN     PB4     /* panel button, to ground, internal pull-up */
#define PIN_LED     PB1

/* Invariants the compiler can enforce, so a bad edit fails the build rather than the
 * experiment. The first one is not hypothetical: burst() computes
 * SPACING_MS - PULSE_MS in uint16_t, so swapping those two constants would not error --
 * it would wrap to ~65 s of silence between pulses, and the only symptom would be that
 * calfinder quietly stopped finding bursts months later. */
_Static_assert(PULSE_MS < SPACING_MS,
               "PULSE_MS must be shorter than SPACING_MS or burst() underflows");
_Static_assert(N_PULSES >= 2, "a single pulse is not a recognisable signature");
_Static_assert(PIN_INJ != PIN_LED && PIN_INJ != PIN_BTN && PIN_LED != PIN_BTN,
               "the three pins must be distinct");
_Static_assert(PIN_BTN != PB5, "PB5 is RESET -- see the RSTDISBL note in the BOM");
_Static_assert(SOAK_H > 0 && PERIOD_H > 0, "zero-length schedule");

static volatile uint8_t button_hit;

ISR(WDT_vect) { }                    /* wake only */
ISR(PCINT0_vect) { button_hit = 1; }

/* One watchdog period is 8 s, the longest available. Everything else is counted. */
#define TICKS_PER_HOUR  450U         /* 3600 / 8 */

static void wdt_8s(void)
{
    cli();
    wdt_reset();
    MCUSR = 0;
    WDTCR = (1 << WDCE) | (1 << WDE);            /* timed sequence to change it */
    WDTCR = (1 << WDIE) | (1 << WDP3) | (1 << WDP0);   /* interrupt, no reset, 8 s */
    sei();
}

/* Sleep for `ticks` watchdog periods, or until the button is pressed. Returns 1 if
 * the button cut it short. */
static uint8_t nap(uint16_t ticks)
{
    while (ticks--) {
        wdt_8s();
        set_sleep_mode(SLEEP_MODE_PWR_DOWN);
        sleep_mode();
        if (button_hit)
            return 1;
    }
    return 0;
}

/* Returns 1 if the button cut the sleep short. */
static uint8_t nap_hours(uint16_t hours)
{
    while (hours--) {
        if (nap(TICKS_PER_HOUR))
            return 1;
    }
    return 0;
}

static void delay_ms_n(uint16_t ms)
{
    while (ms--)
        _delay_ms(1);
}


/* Wait for the button to come up; return 1 if it was held past LONG_PRESS_MS.
 * The LED follows the button so there is feedback while deciding. */
static uint8_t held_long(void)
{
    uint16_t ms = 0;
    delay_ms_n(30);                                  /* debounce the edge */
    while (!(PINB & (1 << PIN_BTN))) {               /* active low, internal pull-up */
        delay_ms_n(10);
        ms += 10;
        if (ms >= LONG_PRESS_MS) {
            PORTB |= (1 << PIN_LED);                 /* long press registered */
            while (!(PINB & (1 << PIN_BTN)))
                delay_ms_n(10);                      /* wait for release */
            PORTB &= (uint8_t) ~(1 << PIN_LED);
            return 1;
        }
    }
    return 0;
}


/* The signature: N_PULSES closures of PULSE_MS, starting SPACING_MS apart.
 *
 * Each closure puts TWO steps into the coil -- current on, then current off -- which
 * is why calfinder.py looks for a step pair PULSE_MS apart inside each repeat, and
 * why the injected level does not have to be known to fit the ring-down: the release
 * is what it fits. The LED is on only while the switch is closed, so the box visibly
 * does something during the acceptance test and is dark the rest of the time.
 */
static void burst(void)
{
    for (uint8_t i = 0; i < N_PULSES; i++) {
        PORTB |= (1 << PIN_INJ) | (1 << PIN_LED);
        delay_ms_n(PULSE_MS);
        PORTB &= (uint8_t) ~((1 << PIN_INJ) | (1 << PIN_LED));
        if (i + 1 < N_PULSES)
            delay_ms_n(SPACING_MS - PULSE_MS);
    }
}

int main(void)
{
    /* Everything off and quiet. Unused pins get pull-ups so no input floats and
     * oscillates, which would cost more standby current than the CPU does. */
    DDRB = (1 << PIN_INJ) | (1 << PIN_LED);
    PORTB = (1 << PIN_BTN) | (1 << PB0) | (1 << PB2);

    ADCSRA &= (uint8_t) ~(1 << ADEN);       /* the ADC alone is ~200 uA if left on */
    ACSR |= (1 << ACD);                     /* analogue comparator off too */
    /* no power_all_off() on the tiny85 -- PRR is the whole story */
    PRR = (1 << PRTIM1) | (1 << PRTIM0) | (1 << PRUSI) | (1 << PRADC);

    GIMSK |= (1 << PCIE);                   /* wake on the button */
    PCMSK |= (1 << PIN_BTN);
    sei();

    /* The soak is firmware-enforced because "just leave it unpowered for two days" is
     * the sort of instruction that gets skipped on the day the box is finished. */
    uint8_t soaking = 1;

    for (;;) {
        if (soaking) {
            if (nap_hours(SOAK_H)) {          /* button cut the soak short */
                button_hit = 0;
                if (!held_long())
                    continue;                 /* short press: soak starts over */
                soaking = 0;                  /* long press: begin firing now */
            } else {
                soaking = 0;                  /* soak completed on its own */
            }
        }

        burst();

        if (nap_hours(PERIOD_H)) {            /* button during the wait */
            button_hit = 0;
            if (!held_long())
                soaking = 1;                  /* short press: back into the soak */
            /* long press: fall through and burst again immediately */
        }
    }
}
