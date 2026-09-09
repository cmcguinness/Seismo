#include "scratch.h"
#include <esp_heap_caps.h>

static char *buf = NULL;

bool scratch_init(void)
{
    if (!buf) buf = (char *)heap_caps_malloc(SCRATCH_SIZE, MALLOC_CAP_SPIRAM);
    return buf != NULL;
}
char  *scratch(void)      { return buf; }
size_t scratch_size(void) { return SCRATCH_SIZE; }
