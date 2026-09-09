#include "scratch.h"
#include <esp_heap_caps.h>
#include <Arduino.h>

static char *buf = NULL;

bool scratch_init(void)
{
    if (buf) return true;

    // INTERNAL SRAM, not PSRAM -- the opposite of the obvious choice, and for a
    // specific reason. The network task fills this buffer on core 0 while the
    // LCD is scanning its framebuffer out of PSRAM on the other core. Putting
    // the buffer in PSRAM meant every HTTP body competed directly with the
    // display's continuous ~15 MB/s read, and the bounce-buffer refill lost the
    // race often enough to stripe the top of the frame constantly.
    //
    // We can afford it now only because dropping TLS freed ~44 KB of internal
    // SRAM. If internal is ever short again, PSRAM is the fallback and the
    // display glitching is the symptom to expect.
    // PSRAM. Internal was tried on the theory that the network task's writes
    // competed with scanout; the A/B disproved it (an idle task is clean at any
    // memory placement, a busy one glitches at all of them). Internal SRAM buys
    // far more as bounce-buffer depth than as a network staging buffer.
    buf = (char *)heap_caps_malloc(SCRATCH_SIZE, MALLOC_CAP_SPIRAM);
    return buf != NULL;
}
char  *scratch(void)      { return buf; }
size_t scratch_size(void) { return SCRATCH_SIZE; }
