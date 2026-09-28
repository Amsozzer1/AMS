# Firmware

The spool-module firmware is its own repository:
**[Amsozzer1/AMS-Firmware](https://github.com/Amsozzer1/AMS-Firmware)**.

One ESP32 drives up to eight modules over a shared step/dir bus, with a per-module enable pin
so that "exactly one spool is energised" is a property of the wiring rather than a promise in
code. The pin map arrives over MQTT and is validated before anything is configured.

[One ESP32, eight spools, two legs per filament move](https://amsozzer.com/writing/a-filament-move-is-two-legs)
is the write-up, including what does not work yet.

This directory used to hold a PlatformIO scaffold. It was an OLED test sketch that never became
the firmware, and it described a cluster of ~16 modules where the real one is 8, so it was
removed rather than left to contradict the repo it points at.
