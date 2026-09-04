/* bench.c -- the mule's instrument: a 32-bit microsecond clock, an edge log, and a
 * serial port to report them on. Compiled only for the ATmega328P; see bench.h.
 *
 * WHAT THIS MEASURES, AND WHAT IT DOES NOT. Timer1 and the delay loops in burst() are
 * driven by the same 16 MHz crystal, so this cannot tell you whether that crystal is
 * accurate -- it is the clock checking itself. What it CAN tell you is everything the
 * software contributes on top: the per-millisecond overhead of delay_ms_n()'s loop,
 * the cost of the PORTB writes, and above all whether the pulse train has the SHAPE
 * the protocol says it does. That last one is the whole reason the mule exists. The
 * failure mode this is built to catch is the one calibrator.c's static assert warns
 * about -- SPACING_MS - PULSE_MS underflowing a uint16_t into ~65 s of silence -- a
 * bug whose only symptom in the field would be calfinder.py quietly finding nothing,
 * months later, with the box sealed and on a shelf.
 *
 * Absolute accuracy is not a thing the flight firmware has or wants: the tiny85 runs
 * off an uncalibrated RC oscillator and calfinder.py measures the spacing rather than
 * assuming it. See the TIMEKEEPING IS DELIBERATELY BAD note in calibrator.c.
 *
 * IF YOU WANT THE ELECTRICAL EDGE rather than the software's idea of it: jumper D11
 * (PB3, the injector) to D8 (PB0, ICP1) and use Timer1 input capture. That measures
 * the pin, including any rise time the PhotoMOS gate adds, and costs one wire. PB0 is
 * left free in hal.h for exactly this. Not done yet -- the software trace found what
 * we were looking for first.
 */
#include "bench.h"

#ifdef CALIBRATOR_MULE

#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>

/* ---------------- clock ----------------
 * Timer1 with the /64 prescaler is 4 us per tick at 16 MHz and overflows every 262 ms;
 * the overflow counter extends that to 32 bits, which is 4.7 hours before it wraps.
 * A burst is 4.5 seconds, so there is no wrap to worry about inside one.
 */
#define TICK_US     4U
#define PRESCALE    ((1 << CS11) | (1 << CS10))     /* clk/64 */

static volatile uint16_t t1_ovf;
static volatile uint16_t wdt_ticks;   /* watchdog periods since boot */
static uint8_t tx_pending;            /* is there a frame still on the wire? */

ISR(TIMER1_OVF_vect) { t1_ovf++; }

/* The standard careful read: the low half and the overflow count must be sampled
 * consistently, and an overflow that fired between the two reads has to be folded in
 * by hand. The `c < 0x8000` test distinguishes "overflowed just now, ISR has not run
 * yet" from "the flag is stale". */
static uint32_t now_ticks(void)
{
    uint8_t s = SREG;
    cli();
    uint16_t c = TCNT1;
    uint16_t o = t1_ovf;
    if ((TIFR1 & (1 << TOV1)) && c < 0x8000)
        o++;
    SREG = s;
    return ((uint32_t) o << 16) | c;
}

/* ---------------- serial ----------------
 * 115200 8N1 with U2X0, which is what the Arduino bootloader already uses, so the
 * same `screen`/`cat` session that flashes the board can read it.
 */
#define BAUD_UBRR   ((F_CPU / (8UL * 115200UL)) - 1UL)

static void uart_putc(char c)
{
    while (!(UCSR0A & (1 << UDRE0)))
        ;
    UDR0 = (uint8_t) c;
    tx_pending = 1;
}

static void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n')
            uart_putc('\r');
        uart_putc(*s++);
    }
}

/* No printf: stdio would cost about 1.5 kB of flash to render integers we can render
 * in twenty lines, and the mule should stay a thing you can read end to end. */
static void uart_putu32(uint32_t v)
{
    char buf[11];
    uint8_t i = 0;
    if (v == 0) {
        uart_putc('0');
        return;
    }
    while (v) {
        buf[i++] = (char) ('0' + (v % 10));
        v /= 10;
    }
    while (i)
        uart_putc(buf[--i]);
}

/* Fixed point, three decimals: microseconds printed as milliseconds. */
static void uart_put_ms(uint32_t us)
{
    uart_putu32(us / 1000UL);
    uart_putc('.');
    uint16_t frac = (uint16_t) (us % 1000UL);
    uart_putc((char) ('0' + frac / 100));
    uart_putc((char) ('0' + (frac / 10) % 10));
    uart_putc((char) ('0' + frac % 10));
}

/* ---- sleep, and why the mule needs to know about it ----
 *
 * The flight firmware spends all but a few seconds a day in SLEEP_MODE_PWR_DOWN, and
 * two things about that are inconvenient for an instrument.
 *
 * First, power-down stops every clock, so TIMER1 -- the microsecond clock above --
 * does not advance while asleep. now_ticks() therefore measures AWAKE time only, and
 * a bench_note() timestamp taken across a nap would silently report 21 ms for an 8
 * second sleep. It did, and it was convincing, which is the dangerous kind of wrong.
 * The honest fix is to report the two quantities the mule can actually measure: how
 * many watchdog periods have elapsed (counted in the WDT interrupt) and how long the
 * chip has been awake (Timer1). Their sum is the schedule. Note what this can and
 * cannot check: it verifies that nap()/nap_hours() count the RIGHT NUMBER of periods,
 * which is the part that is logic and can be wrong. It cannot verify that a period is
 * 8.000 s, because the watchdog runs off an RC oscillator here exactly as it does on
 * the tiny -- and per the TIMEKEEPING note in calibrator.c, we do not care.
 *
 * Second, the USART is unclocked in power-down and the transmitter emits a transient
 * on the way in or out -- about fourteen junk bytes on the wire, straddling the sleep.
 * Draining first is necessary but NOT sufficient: bench_drain() waits on TXC0, which
 * is the shift register going empty, so the AVR really has finished before it sleeps,
 * and the junk still appears. So the transmitter is switched off around the nap, with
 * PD1 held high by hand to keep the line at its idle level while it is off, and given
 * a couple of milliseconds to settle on the way back. That is a mule-only wart: the
 * flight build has no USART to protect and these functions compile to nothing.
 */
/* The ORDER of these four lines is the whole point, and getting it wrong is worth
 * exactly three junk bytes per nap. TXEN0 owns PD1 while it is set; the moment it is
 * cleared the pin reverts to whatever DDRD/PORTD say, and at reset that is "input, no
 * pull-up" -- floating. So claim the pin as a driven output FIRST and hand it over
 * SECOND, and reverse that on the way back. Never leave a gap where nobody is driving
 * the line: a floating TXD reads as a start bit to the bridge at the other end. */
void bench_sleep_enter(void)
{
    /* One real frame on each side of the nap. See the note in bench_sleep_exit(). */
    uart_putc('\r');
    bench_drain();
    PORTD |= (1 << PD1);            /* hold TXD at idle (mark)... */
    DDRD  |= (1 << PD1);            /* ...as a plain output, before... */
    UCSR0B &= (uint8_t) ~(1 << TXEN0);  /* ...the USART lets go of it */
}

void bench_sleep_exit(void)
{
    _delay_ms(2);                   /* let the oscillator settle before it is a baud rate */
    UCSR0B |= (1 << TXEN0);         /* USART takes the pin back while it is still driven */
    DDRD  &= (uint8_t) ~(1 << PD1);

    /* THE JUNK BYTES, and what actually fixed them. Sleeping put a burst of garbage on
     * the wire -- fourteen bytes per nap, straddling the sleep. Three things were
     * measured, in this order, because each one only half worked:
     *
     *   1. Park PD1 as a driven output BEFORE clearing TXEN0 (and reverse it on the
     *      way back), so the pin is never floating during the handover. 14 -> 3.
     *   2. Send a frame AFTER re-enabling the transmitter. On its own this makes it
     *      WORSE -- 13 -- because that frame is itself the one that gets corrupted.
     *   3. Send a frame BEFORE parking as well. Zero, over twelve naps.
     *
     * So the transient is not one event but two, one at each edge of the nap, and each
     * is absorbed by a real frame adjacent to it -- the first byte across a TXEN0
     * transition is the one that gets eaten, and it might as well be a throwaway. A
     * bare carriage return is the ideal throwaway: it is a complete frame, and it is
     * invisible in a terminal because it only returns the cursor to the start of a
     * line that is already empty.
     *
     * The mechanism at the silicon level was never pinned down and does not need to
     * be; what matters is that the numbers above are reproducible, and that this is
     * mule-only -- the flight build has no USART for any of it to happen to. */
    uart_putc('\r');
    bench_drain();
}

/* Called from ISR(WDT_vect) in calibrator.c, so it must stay this cheap. */
void bench_wdt_tick(void)
{
    wdt_ticks++;
}

/* UDRE only says the data register is free; TXC says the last bit has actually left
 * the shift register, which is the one that matters before the clock stops.
 *
 * The tx_pending guard is not decoration. TXC is cleared here after it is observed, so
 * a SECOND drain with nothing sent in between would wait forever for a completion that
 * has already happened and been consumed -- and bench_sleep_enter() drains, which is
 * exactly a second drain every time a bench_note() precedes a nap. That deadlock cost
 * an afternoon; the flag costs a byte. */
void bench_drain(void)
{
    if (!tx_pending)
        return;
    while (!(UCSR0A & (1 << TXC0)))
        ;
    UCSR0A |= (1 << TXC0);      /* TXC is cleared by writing one to it */
    tx_pending = 0;
}

/* ---------------- edge log ---------------- */
#define MAX_EDGES   16          /* 2 per pulse; 8 pulses is more than the protocol asks */

static uint32_t edge_t[MAX_EDGES];
static uint8_t  edge_n;
static uint32_t burst_t0;

void bench_init(void)
{
    UBRR0H = (uint8_t) (BAUD_UBRR >> 8);
    UBRR0L = (uint8_t) BAUD_UBRR;
    UCSR0A = (1 << U2X0);
    UCSR0B = (1 << TXEN0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);     /* 8N1 */

    TCCR1A = 0;
    TCCR1B = PRESCALE;
    TIMSK1 = (1 << TOIE1);

    uart_puts("\n--- calibrator bench mule (ATmega328P) ---\n"
              "injector D11/PB3, button D12/PB4 to GND, LED D13 onboard\n");
    bench_drain();
}

void bench_burst_begin(void)
{
    edge_n = 0;
    burst_t0 = now_ticks();
}

/* Called immediately after the PORTB write, so it is inside the pulse it is timing.
 * The read is about 2 us against a 500 ms pulse -- four parts per million, and it
 * lands the same way on both edges, so the widths it reports are unbiased. */
void bench_mark(uint8_t level)
{
    (void) level;
    if (edge_n < MAX_EDGES)
        edge_t[edge_n++] = now_ticks();
}

static void check(const char *label, uint32_t got_us, uint32_t want_ms)
{
    /* One percent is far tighter than anything downstream needs and far looser than
     * the software error we are hunting, which is either ~zero or catastrophic. */
    uint32_t want_us = want_ms * 1000UL;
    uint32_t slop = want_us / 100UL;
    uint32_t d = got_us > want_us ? got_us - want_us : want_us - got_us;

    uart_puts(d <= slop ? "  PASS  " : "  FAIL  ");
    uart_puts(label);
    uart_puts(" = ");
    uart_put_ms(got_us);
    uart_puts(" ms (want ");
    uart_putu32(want_ms);
    uart_puts(")\n");
}

void bench_burst_end(uint8_t n_pulses, uint16_t pulse_ms, uint16_t spacing_ms)
{
    uart_puts("\nburst: ");
    uart_putu32(edge_n / 2);
    uart_puts(" pulses logged, want ");
    uart_putu32(n_pulses);
    uart_puts("\n");

    for (uint8_t i = 0; i + 1 < edge_n; i += 2) {
        uint32_t on  = (edge_t[i]     - burst_t0) * TICK_US;
        uint32_t off = (edge_t[i + 1] - burst_t0) * TICK_US;

        uart_puts("  pulse ");
        uart_putu32(i / 2U + 1U);
        uart_puts(": close at ");
        uart_put_ms(on);
        uart_puts(" ms, open at ");
        uart_put_ms(off);
        uart_puts(" ms\n");
    }

    if (edge_n != (uint8_t) (2 * n_pulses)) {
        uart_puts("  FAIL  edge count\n");
        bench_drain();
        return;
    }

    /* Width of every pulse, and the start-to-start interval between them. Those two
     * are the entire signature calfinder.py looks for. */
    for (uint8_t i = 0; i < n_pulses; i++)
        check("width", (edge_t[2 * i + 1] - edge_t[2 * i]) * TICK_US, pulse_ms);

    for (uint8_t i = 1; i < n_pulses; i++)
        check("spacing", (edge_t[2 * i] - edge_t[2 * (i - 1)]) * TICK_US, spacing_ms);

    uart_puts("\n");
    bench_drain();
}

void bench_note(const char *msg)
{
    /* The tick count is 16-bit and incremented in an ISR, so it is not atomic to read
     * on an 8-bit machine -- and the watchdog does fire while awake, inside
     * held_long(). Guard it rather than hope. */
    uint8_t s = SREG;
    cli();
    uint16_t ticks = wdt_ticks;
    SREG = s;

    uart_puts("[wdt ");
    uart_putu32(ticks);
    uart_puts(" (");
    uart_putu32((uint32_t) ticks * 8UL);
    uart_puts(" s nominal), awake ");
    uart_put_ms(now_ticks() * TICK_US);
    uart_puts(" ms] ");
    uart_puts(msg);
    uart_puts("\n");
    bench_drain();
}

#endif /* CALIBRATOR_MULE */
