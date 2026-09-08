"""Strip host-toolchain include paths before the cross-compiler runs.

~/.zshrc exports CPLUS_INCLUDE_PATH (and friends) pointing at Apple's libc++
headers. GCC honours those variables for EVERY target, so the xtensa-esp32s3
cross-compiler picks up macOS system headers and dies with

    .../MacOSX.sdk/usr/include/c++/v1/__config:704: error: "No thread API"

.zshrc's own `get_idf` alias unsets them for ESP-IDF; PlatformIO never goes
through that alias, so it has to defend itself. Do not remove this without
checking whether that export is still in the shell profile.
"""

import os

Import("env")  # noqa: F821  (injected by SCons)

POISON = (
    "CPATH",
    "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH",
    "OBJC_INCLUDE_PATH",
    "OBJCPLUS_INCLUDE_PATH",
    "SDKROOT",
    "LIBRARY_PATH",
)

dropped = [v for v in POISON if os.environ.pop(v, None) is not None]
if dropped:
    print("clean_host_env: dropped host include vars -> %s" % ", ".join(dropped))
