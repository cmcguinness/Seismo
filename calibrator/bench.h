/* bench.h -- instrumentation that exists ONLY on the bench mule.
 *
 * On the flight target every one of these is an empty macro, so calibrator.c can call
 * them unconditionally and the ATtiny85 build is byte-identical to one with no
 * instrumentation in it at all. Check that claim rather than trusting it:
 *
 *      make clean && make && avr-size calibrator.elf
 *
 * against the size before these calls were added (162 -> unchanged).
 */
#ifndef CALIBRATOR_BENCH_H
#define CALIBRATOR_BENCH_H

#include "hal.h"

#ifdef CALIBRATOR_MULE

#include <stdint.h>

void bench_init(void);
void bench_burst_begin(void);
void bench_mark(uint8_t level);     /* record an injector edge, 1 = closed */
void bench_burst_end(uint8_t n_pulses, uint16_t pulse_ms, uint16_t spacing_ms);
void bench_note(const char *msg);   /* a state-machine event, e.g. "soak done" */
void bench_drain(void);             /* let the UART finish before power-down */
void bench_sleep_enter(void);
void bench_sleep_exit(void);
void bench_wdt_tick(void);

#define BENCH_INIT()          bench_init()
#define BENCH_BURST_BEGIN()   bench_burst_begin()
#define BENCH_MARK(level)     bench_mark(level)
#define BENCH_BURST_END(n, p, s)  bench_burst_end((n), (p), (s))
#define BENCH_NOTE(msg)       bench_note(msg)
#define BENCH_DRAIN()         bench_drain()
#define BENCH_SLEEP_ENTER()   bench_sleep_enter()
#define BENCH_SLEEP_EXIT()    bench_sleep_exit()
#define BENCH_WDT_TICK()      bench_wdt_tick()

#else

#define BENCH_INIT()              ((void) 0)
#define BENCH_BURST_BEGIN()       ((void) 0)
#define BENCH_MARK(level)         ((void) 0)
#define BENCH_BURST_END(n, p, s)  ((void) 0)
#define BENCH_NOTE(msg)           ((void) 0)
#define BENCH_DRAIN()             ((void) 0)
#define BENCH_SLEEP_ENTER()       ((void) 0)
#define BENCH_SLEEP_EXIT()        ((void) 0)
#define BENCH_WDT_TICK()          ((void) 0)

#endif

#endif /* CALIBRATOR_BENCH_H */
