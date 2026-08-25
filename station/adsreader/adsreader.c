/*
 * adsreader.c — own the ADS1256 and stream timestamped samples to stdout.
 *
 * WHY THIS EXISTS (STATUS.md 2026-08-25, "RECORDER"): the Python read loop at 100 sps
 * on a Pi 2B is late ~0.2 % of the time, and when it is late the chip's unread-data
 * DRDY pulse is too short for pigpiod's 5 us sampler to see, so the conversion is lost
 * SILENTLY: not counted, not timed, just gone. The archive got a 0.2 % time-stretch
 * inside every block, an 18 ms gap after it, and a 0.1 Hz comb on every sub-Hz
 * spectrum. Two things fix that, and both are easy here and hard in Python:
 *
 *   1. DRDY as a KERNEL INTERRUPT (GPIO character-device uAPI v2), not a sampled
 *      level. Every falling edge is queued with a hardware timestamp and a per-line
 *      sequence number, so a late read finds the events waiting and knows EXACTLY how
 *      many conversions it missed.
 *   2. A buffer between the 10 ms deadline and everything else. This process does
 *      nothing but wait / read 3 bytes / write 16 bytes; the pipe to Python absorbs
 *      Python's stalls (the recorder sets it to 1 MB, ~17 min at 100 sps).
 *
 * It also applies SCHED_FIFO and mlockall on itself if the limits allow (the
 * systemd unit grants them; otherwise it warns and runs as a normal process).
 *
 * OWNERSHIP: this process owns the chip end to end -- reset, register setup, SELFCAL,
 * RDATAC -- via /dev/spidev0.0 and /dev/gpiochip0. Nothing else may touch the ADS1256
 * while it runs (pigpiod may keep running for other tools, but adc_diag & co. must not
 * open the ADC). The Waveshare board's chip select is GPIO22, NOT the SPI controller's
 * CE0, so CS is driven by hand (held low for the whole RDATAC session, like the
 * Python reader's hold_cs) and spidev is opened with SPI_NO_CS.
 *
 * OUTPUT: 16-byte little-endian records on stdout, one per DRDY edge serviced:
 *     u64 ts_ns    CLOCK_REALTIME nanoseconds of the DRDY falling edge (kernel IRQ time)
 *     s32 sample   24-bit conversion, sign-extended
 *     u16 lost     conversions missed since the previous record (line_seqno gap)
 *     u16 flags    bit0 = read landed in the chip's update window (value unreliable);
 *                  bit1 = all-zero frame
 * stderr gets a one-line banner and errors. Exit codes: 2 = wrong chip ID / setup,
 * 3 = DRDY stopped, 4 = write failed (reader went away).
 *
 *     adsreader [--gain 64] [--sps 100] [--spi /dev/spidev0.0] [--chip /dev/gpiochip0]
 *
 * Build: make (gcc -O2 -Wall). No libraries beyond libc and the kernel headers.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <linux/gpio.h>
#include <linux/spi/spidev.h>

/* --- Waveshare High-Precision AD/DA board wiring (station/waveshare_config.py) --- */
#define PIN_DRDY   17
#define PIN_RESET  18
#define PIN_CS     22
#define PIN_CS_DAC 23      /* DAC8532 on the same bus: hold ITS CS high too */
#define PIN_PDWN   27
#define SPI_HZ     976563  /* the validated bring-up rate */

/* ADS1256 registers and commands */
#define REG_STATUS 0x00
#define CMD_WAKEUP 0x00
#define CMD_RDATAC 0x03
#define CMD_SDATAC 0x0F
#define CMD_RREG   0x10
#define CMD_WREG   0x50
#define CMD_SELFCAL 0xF0
#define CMD_SYNC   0xFC
#define CMD_RESET  0xFE
#define CHIP_ID    3

#define DRDY_TIMEOUT_MS 2000
#define EVENT_BUF 64

struct __attribute__((packed)) record {
    uint64_t ts_ns;
    int32_t  sample;
    uint16_t lost;
    uint16_t flags;
};

static volatile sig_atomic_t g_stop = 0;
static void on_signal(int sig) { (void)sig; g_stop = 1; }

static int g_spi = -1, g_out = -1, g_ev = -1;

static void die(int code, const char *msg) {
    fprintf(stderr, "adsreader: %s%s%s\n", msg, errno ? ": " : "", errno ? strerror(errno) : "");
    exit(code);
}

static void msleep(long ms) {
    struct timespec ts = { ms / 1000, (ms % 1000) * 1000000L };
    nanosleep(&ts, NULL);
}

/* ---------------------------------------------------------------- GPIO uAPI v2 -- */

static int chip_request_outputs(int chip, const unsigned *pins, const int *vals, int n) {
    struct gpio_v2_line_request req;
    memset(&req, 0, sizeof req);
    for (int i = 0; i < n; i++) req.offsets[i] = pins[i];
    req.num_lines = n;
    strncpy(req.consumer, "adsreader", sizeof req.consumer - 1);
    req.config.flags = GPIO_V2_LINE_FLAG_OUTPUT;
    req.config.num_attrs = 1;
    req.config.attrs[0].attr.id = GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES;
    uint64_t bits = 0, mask = 0;
    for (int i = 0; i < n; i++) { mask |= 1ULL << i; if (vals[i]) bits |= 1ULL << i; }
    req.config.attrs[0].attr.values = bits;
    req.config.attrs[0].mask = mask;
    if (ioctl(chip, GPIO_V2_GET_LINE_IOCTL, &req) < 0) return -1;
    return req.fd;
}

static int chip_request_drdy(int chip) {
    struct gpio_v2_line_request req;
    memset(&req, 0, sizeof req);
    req.offsets[0] = PIN_DRDY;
    req.num_lines = 1;
    strncpy(req.consumer, "adsreader-drdy", sizeof req.consumer - 1);
    req.config.flags = GPIO_V2_LINE_FLAG_INPUT | GPIO_V2_LINE_FLAG_EDGE_FALLING
                     | GPIO_V2_LINE_FLAG_EVENT_CLOCK_REALTIME;
    req.event_buffer_size = EVENT_BUF;
    if (ioctl(chip, GPIO_V2_GET_LINE_IOCTL, &req) < 0) return -1;
    return req.fd;
}

static int line_set(int fd, int idx, int val) {
    struct gpio_v2_line_values v = { .bits = val ? (1ULL << idx) : 0, .mask = 1ULL << idx };
    return ioctl(fd, GPIO_V2_LINE_SET_VALUES_IOCTL, &v);
}

static int line_get(int fd, int idx) {
    struct gpio_v2_line_values v = { .bits = 0, .mask = 1ULL << idx };
    if (ioctl(fd, GPIO_V2_LINE_GET_VALUES_IOCTL, &v) < 0) return -1;
    return (v.bits >> idx) & 1;
}

/* output line request order: CS, CS_DAC, RESET, PDWN */
enum { O_CS = 0, O_CSDAC, O_RESET, O_PDWN };
static int g_outs = -1;
static void cs(int low) { line_set(g_outs, O_CS, low ? 0 : 1); }

/* --------------------------------------------------------------------- SPI ------ */

static int spi_xfer(const uint8_t *tx, uint8_t *rx, unsigned len, unsigned delay_us) {
    struct spi_ioc_transfer t;
    memset(&t, 0, sizeof t);
    t.tx_buf = (unsigned long)tx;
    t.rx_buf = (unsigned long)rx;
    t.len = len;
    t.speed_hz = SPI_HZ;
    t.bits_per_word = 8;
    t.delay_usecs = delay_us;
    return ioctl(g_spi, SPI_IOC_MESSAGE(1), &t) < 0 ? -1 : 0;
}

/* one command byte with CS cycled around it (the Python _soft_reset idiom) */
static void cmd_cycled(uint8_t c) {
    cs(1); spi_xfer(&c, NULL, 1, 0); msleep(2); cs(0); msleep(1);
}

static int read_status(void) {
    uint8_t tx[2] = { CMD_RREG | REG_STATUS, 0x00 }, rx[1] = { 0 };
    cs(1);
    if (spi_xfer(tx, NULL, 2, 7) < 0) { cs(0); return -1; }   /* t6 = 50 tCLKIN ≈ 6.5 us */
    if (spi_xfer(NULL, rx, 1, 0) < 0) { cs(0); return -1; }
    cs(0);
    return rx[0];
}

static int wait_drdy_low(int timeout_ms) {
    for (int i = 0; i < timeout_ms; i++) {
        int v = line_get(g_ev, 0);
        if (v == 0) return 0;
        msleep(1);
    }
    return -1;
}

static int drate_code(double sps) {
    static const struct { double sps; int code; } tab[] = {
        {30000, 0xF0}, {15000, 0xE0}, {7500, 0xD0}, {3750, 0xC0}, {2000, 0xB0},
        {1000, 0xA1}, {500, 0x92}, {100, 0x82}, {60, 0x72}, {50, 0x63}, {30, 0x53},
        {25, 0x43}, {15, 0x33}, {10, 0x23}, {5, 0x13}, {2.5, 0x03}, {0, 0} };
    for (int i = 0; tab[i].sps; i++) if (tab[i].sps == sps) return tab[i].code;
    return -1;
}

static void chip_release(void) {
    /* Documented exit from RDATAC: SDATAC (twice, mid-frame safe) then RESET, so the
       next opener does not read stream data where it expects the ID register. */
    if (g_spi < 0 || g_outs < 0) return;
    uint8_t c;
    c = CMD_SDATAC; cmd_cycled(c); cmd_cycled(c);
    c = CMD_RESET;  cmd_cycled(c);
    msleep(30);
    cs(0);
}

/* ---------------------------------------------------------------------- main ---- */

int main(int argc, char **argv) {
    int gain = 64; double sps = 100; const char *spidev = "/dev/spidev0.0", *chipdev = "/dev/gpiochip0";
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--gain") && i + 1 < argc) gain = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--sps") && i + 1 < argc) sps = atof(argv[++i]);
        else if (!strcmp(argv[i], "--spi") && i + 1 < argc) spidev = argv[++i];
        else if (!strcmp(argv[i], "--chip") && i + 1 < argc) chipdev = argv[++i];
        else { fprintf(stderr, "usage: adsreader [--gain N] [--sps N] [--spi DEV] [--chip DEV]\n"); return 1; }
    }
    int pga = 0; { int g = gain; if (g < 1 || g > 64 || (g & (g - 1))) die(1, "gain must be 1,2,4,...,64"); while (g > 1) { g >>= 1; pga++; } }
    int drate = drate_code(sps);
    if (drate < 0) die(1, "unsupported --sps");

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    signal(SIGPIPE, SIG_IGN);

    /* real-time-ish: best effort, warn only */
    struct sched_param sp = { .sched_priority = 50 };
    if (sched_setscheduler(0, SCHED_FIFO, &sp) < 0)
        fprintf(stderr, "adsreader: SCHED_FIFO not granted (%s); running at normal priority\n", strerror(errno));
    if (mlockall(MCL_CURRENT | MCL_FUTURE) < 0)
        fprintf(stderr, "adsreader: mlockall failed (%s); continuing\n", strerror(errno));
    errno = 0;

    int chip = open(chipdev, O_RDWR | O_CLOEXEC);
    if (chip < 0) die(2, "open gpiochip");
    const unsigned opins[4] = { PIN_CS, PIN_CS_DAC, PIN_RESET, PIN_PDWN };
    const int ovals[4] = { 1, 1, 1, 1 };
    g_outs = chip_request_outputs(chip, opins, ovals, 4);
    if (g_outs < 0) die(2, "request output lines (CS/RESET/PDWN)");
    g_ev = chip_request_drdy(chip);
    if (g_ev < 0) die(2, "request DRDY edge events");
    close(chip);

    g_spi = open(spidev, O_RDWR | O_CLOEXEC);
    if (g_spi < 0) die(2, "open spidev");
    uint8_t mode = SPI_MODE_1 | SPI_NO_CS;
    if (ioctl(g_spi, SPI_IOC_WR_MODE, &mode) < 0) die(2, "SPI mode");
    uint8_t bpw = 8; uint32_t hz = SPI_HZ;
    if (ioctl(g_spi, SPI_IOC_WR_BITS_PER_WORD, &bpw) < 0) die(2, "SPI bits");
    if (ioctl(g_spi, SPI_IOC_WR_MAX_SPEED_HZ, &hz) < 0) die(2, "SPI speed");
    g_out = STDOUT_FILENO;

    /* --- bring the chip to a known state: SDATAC x2, RESET, settle --- */
    msleep(30);
    cmd_cycled(CMD_SDATAC); cmd_cycled(CMD_SDATAC); cmd_cycled(CMD_RESET);
    msleep(200);
    int st = read_status();
    if (st < 0) die(2, "RREG STATUS");
    if ((st >> 4) != CHIP_ID) {
        fprintf(stderr, "adsreader: wrong chip ID %d (STATUS 0x%02x), expected %d\n", st >> 4, st, CHIP_ID);
        return 2;
    }
    /* --- STATUS, MUX, ADCON, DRATE in one WREG (buffer off, AIN0-AIN1, PGA, rate) --- */
    {
        uint8_t w[6] = { CMD_WREG | REG_STATUS, 0x03, 0x00, 0x01, (uint8_t)pga, (uint8_t)drate };
        cs(1); if (spi_xfer(w, NULL, 6, 0) < 0) die(2, "WREG"); cs(0);
        msleep(1);
    }
    /* --- SELFCAL, wait for DRDY --- */
    { uint8_t c = CMD_SELFCAL; cs(1); spi_xfer(&c, NULL, 1, 0); cs(0); }
    if (wait_drdy_low(DRDY_TIMEOUT_MS) < 0) die(2, "SELFCAL never finished (DRDY stuck high)");
    /* --- SYNC / WAKEUP, then hold CS and enter RDATAC --- */
    { uint8_t c = CMD_SYNC;   cs(1); spi_xfer(&c, NULL, 1, 10); cs(0); }
    { uint8_t c = CMD_WAKEUP; cs(1); spi_xfer(&c, NULL, 1, 0);  cs(0); }
    /* drain any edge events queued during setup so seqno accounting starts clean */
    { struct pollfd p = { g_ev, POLLIN, 0 }; struct gpio_v2_line_event ev[EVENT_BUF];
      while (poll(&p, 1, 0) > 0) if (read(g_ev, ev, sizeof ev) <= 0) break; }
    cs(1);
    { uint8_t c = CMD_RDATAC; if (spi_xfer(&c, NULL, 1, 0) < 0) die(2, "RDATAC"); }
    msleep(1);

    fprintf(stderr, "adsreader: ADS1256 id %d, gain %d (PGA %d), %g sps (DRATE 0x%02x), "
                    "%s + %s, streaming\n", st >> 4, gain, pga, sps, drate, spidev, chipdev);

    /* --- the loop: wait for DRDY, read 3 bytes, write 16 --- */
    struct pollfd pfd = { g_ev, POLLIN, 0 };
    struct gpio_v2_line_event ev[EVENT_BUF];
    uint32_t prev_seq = 0; int have_prev = 0;
    const uint8_t tx0[3] = { 0, 0, 0 };
    uint8_t rx[3];
    unsigned long n_out = 0, n_lost = 0, n_flag = 0;
    int rc = 0;

    while (!g_stop) {
        int pr = poll(&pfd, 1, DRDY_TIMEOUT_MS);
        if (pr < 0) { if (errno == EINTR) continue; die(3, "poll"); }
        if (pr == 0) { fprintf(stderr, "adsreader: DRDY stopped -- ADC not converting?\n"); rc = 3; break; }
        ssize_t got = read(g_ev, ev, sizeof ev);
        if (got < (ssize_t)sizeof ev[0]) { if (errno == EINTR) continue; die(3, "read events"); }
        int nev = got / sizeof ev[0];
        const struct gpio_v2_line_event *last = &ev[nev - 1];

        /* how many conversions since the previous serviced one, minus the one we serve */
        uint16_t lost = 0;
        if (have_prev) {
            uint32_t gap = last->line_seqno - prev_seq;     /* >=1 */
            lost = gap > 1 ? (uint16_t)(gap - 1) : 0;
        }
        prev_seq = last->line_seqno; have_prev = 1;

        uint16_t flags = 0;
        /* DRDY high right now means the chip is mid-update: we are a whole period late
           and the frame will clock out garbage (or zeros). Read anyway, but say so. */
        if (line_get(g_ev, 0) == 1) flags |= 1;
        if (spi_xfer(tx0, rx, 3, 0) < 0) die(3, "SPI read");
        int32_t v = ((int32_t)rx[0] << 16) | ((int32_t)rx[1] << 8) | rx[2];
        if (v & 0x800000) v -= 0x1000000;
        if (rx[0] == 0 && rx[1] == 0 && rx[2] == 0) flags |= 2;

        struct record r = { last->timestamp_ns, v, lost, flags };
        const uint8_t *p = (const uint8_t *)&r; size_t left = sizeof r;
        while (left) {
            ssize_t w = write(g_out, p, left);
            if (w < 0) { if (errno == EINTR) continue; fprintf(stderr, "adsreader: stdout gone (%s)\n", strerror(errno)); rc = 4; g_stop = 1; break; }
            p += w; left -= w;
        }
        n_out++; n_lost += lost; if (flags) n_flag++;
    }

    chip_release();
    fprintf(stderr, "adsreader: stopped after %lu samples, %lu lost, %lu flagged\n", n_out, n_lost, n_flag);
    return rc;
}
