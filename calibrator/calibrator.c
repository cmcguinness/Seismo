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
#include "hal.h"      /* F_CPU, the pin map, and the few registers that are named
                       * differently on the bench mule -- see hal.h for why */
#include "bench.h"    /* instrumentation; every macro is empty on the flight build */

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

/* Each calibration is a PAIR of bursts: unshunted, a gap, then shunted. The pair is the
 * measurement -- ringdown.py solves for the generator constant from two zeta values, one
 * of each, and taking them 16 s apart rather than days apart means ground conditions,
 * temperature and background noise are common to both and cancel.
 *
 * The gap is TWO WATCHDOG PERIODS, not a busy-wait: 16 s of _delay_ms would hold the CPU
 * awake at ~300 uA where sleeping costs ~5 uA, and this box is built to last years on a
 * coin cell. It must clear calfinder.py's amp_out probe (2 s before onset, N_PULSES*u
 * after = 6 s) and leave the first ring-down fully dead before the second starts, or the
 * second decay is fitted on the tail of the first. 16 s does both with room to spare. */
#define GAP_TICKS   2       /* watchdog periods between the two bursts of a pair */

/* ---- schedule ---- */
#ifndef SOAK_H
#define SOAK_H      48      /* silence after power-up. Two full diurnal cycles of
                             * "off" before the first burst, so the archive holds a
                             * clean before-picture to compare every later burst
                             * against. Enforced here rather than by remembering not
                             * to install it yet. */
#endif
#ifndef PERIOD_H
#define PERIOD_H    6       /* four bursts a day */
#endif

/* SOAK_H, PERIOD_H and TICKS_PER_HOUR (below) are the only overridable numbers here,
 * and they exist so the bench mule can run this state machine in minutes instead of
 * days -- see the `mule` target in the Makefile. The FLIGHT build must never define
 * them: the whole point of SOAK_H is that it is enforced in firmware rather than by
 * remembering. The PROTOCOL constants above are deliberately NOT overridable, because
 * analysis/calfinder.py reads them straight out of this file and a mule that fired a
 * different signature would be testing something we are not going to ship. */

/* The button is two commands, told apart by how long it is held. A SHORT press
 * RESTARTS the soak; a LONG press fires a burst immediately.
 *
 * That asymmetry is deliberate and it is the safe way round. This box sits on a shelf
 * for months, so the realistic button event is an accidental knock -- and the harmless
 * response to an accident is to start the quiet period again, not to skip it. Firing
 * the injector is the deliberate act, so it is the one that has to be held for. */
#define LONG_PRESS_MS  2000

/* ---- pins ----
 * PIN_INJ, PIN_BTN and PIN_LED live in hal.h, because which pin is which is exactly
 * the sort of thing that differs between the tiny85 and the mule. The reasoning
 * behind the flight assignment -- why the LED is on MISO and not MOSI, and why PB5 is
 * left alone -- is in the comment there.
 */

/* Invariants the compiler can enforce, so a bad edit fails the build rather than the
 * experiment. The first one is not hypothetical: burst() computes
 * SPACING_MS - PULSE_MS in uint16_t, so swapping those two constants would not error --
 * it would wrap to ~65 s of silence between pulses, and the only symptom would be that
 * calfinder quietly stopped finding bursts months later. */
_Static_assert(PULSE_MS < SPACING_MS,
               "PULSE_MS must be shorter than SPACING_MS or burst() underflows");
_Static_assert(N_PULSES >= 2, "a single pulse is not a recognisable signature");
_Static_assert(PIN_INJ != PIN_SHUNT && PIN_INJ != PIN_BTN && PIN_SHUNT != PIN_BTN,
               "the three pins must be distinct");
ASSERT_BTN_NOT_RESET();
_Static_assert(SOAK_H > 0 && PERIOD_H > 0, "zero-length schedule");

static volatile uint8_t button_hit;

ISR(WDT_vect) { BENCH_WDT_TICK(); }  /* wake only (the hook is empty on flight) */
ISR(PCINT0_vect) { button_hit = 1; }

/* One watchdog period is 8 s, the longest available. Everything else is counted. */
#ifndef TICKS_PER_HOUR
#define TICKS_PER_HOUR  450U         /* 3600 / 8 */
#endif

static void wdt_8s(void)
{
    cli();
    wdt_reset();
    MCUSR = 0;
    WDT_CTRL = (1 << WDCE) | (1 << WDE);            /* timed sequence to change it */
    WDT_CTRL = (1 << WDIE) | (1 << WDP3) | (1 << WDP0);   /* interrupt, no reset, 8 s */
    sei();
}

/* Sleep for `ticks` watchdog periods, or until the button is pressed. Returns 1 if
 * the button cut it short. */
static uint8_t nap(uint16_t ticks)
{
    while (ticks--) {
        wdt_8s();
        BENCH_SLEEP_ENTER();
        set_sleep_mode(SLEEP_MODE_PWR_DOWN);
        sleep_mode();
        BENCH_SLEEP_EXIT();
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
            /* The old status LED gave feedback here and its pin is now the shunt, which
             * must not be closed just because somebody held the button. No feedback:
             * the acceptance test is calfinder finding the burst in the archive, which
             * is the only evidence that survives the walk back from the garage. */
            while (!(PINB & (1 << PIN_BTN)))
                delay_ms_n(10);                      /* wait for release */
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
static void burst(uint8_t shunt)
{
    /* The shunt closes BEFORE the first pulse and opens AFTER the last, so it loads the
     * coil for the whole burst and for nothing else. It must never be driven together
     * with PIN_INJ the way the old status LED was -- that would short the coil through
     * the shunt during the injection pulse itself. */
    if (shunt)
        PORTB |= (1 << PIN_SHUNT);
    BENCH_BURST_BEGIN();
    for (uint8_t i = 0; i < N_PULSES; i++) {
        PORTB |= (1 << PIN_INJ);
        BENCH_MARK(1);
        delay_ms_n(PULSE_MS);
        PORTB &= (uint8_t) ~(1 << PIN_INJ);
        BENCH_MARK(0);
        if (i + 1 < N_PULSES)
            delay_ms_n(SPACING_MS - PULSE_MS);
    }
    BENCH_BURST_END(N_PULSES, PULSE_MS, SPACING_MS);
    PORTB &= (uint8_t) ~(1 << PIN_SHUNT);
}


/* One calibration = the pair. Unshunted first, so a run that is interrupted after the
 * first burst still leaves a usable open-circuit measurement rather than a shunted one
 * of unknown provenance. */
static void calibrate_pair(void)
{
    burst(0);
    BENCH_NOTE("gap, then the shunted burst");
    nap(GAP_TICKS);
    burst(1);
}

int main(void)
{
    /* Everything off and quiet. Unused pins get pull-ups so no input floats and
     * oscillates, which would cost more standby current than the CPU does. */
    DDRB = (1 << PIN_INJ) | (1 << PIN_SHUNT);
    PORTB = (1 << PIN_BTN) | PIN_IDLE_PULLUPS;

    ADCSRA &= (uint8_t) ~(1 << ADEN);       /* the ADC alone is ~200 uA if left on */
    ACSR |= (1 << ACD);                     /* analogue comparator off too */
    PRR_SETUP();                            /* every peripheral we do not need, off */

    PCINT_ENABLE();                         /* wake on the button */
    sei();

    BENCH_INIT();

    /* The soak is firmware-enforced because "just leave it unpowered for two days" is
     * the sort of instruction that gets skipped on the day the box is finished. */
    uint8_t soaking = 1;

    for (;;) {
        if (soaking) {
            BENCH_NOTE("soaking");
            if (nap_hours(SOAK_H)) {          /* button cut the soak short */
                button_hit = 0;
                if (!held_long()) {
                    BENCH_NOTE("short press: soak restarts");
                    continue;                 /* short press: soak starts over */
                }
                BENCH_NOTE("long press: fire now");
                soaking = 0;                  /* long press: begin firing now */
            } else {
                BENCH_NOTE("soak completed");
                soaking = 0;                  /* soak completed on its own */
            }
        }

        calibrate_pair();

        if (nap_hours(PERIOD_H)) {            /* button during the wait */
            button_hit = 0;
            if (!held_long()) {
                BENCH_NOTE("short press: back into the soak");
                soaking = 1;                  /* short press: back into the soak */
            } else {
                BENCH_NOTE("long press: burst again now");
            }
            /* long press: fall through and burst again immediately */
        }
    }
}
