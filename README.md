# AVR 161 — network control & custom firmware

Reverse engineering, a network control tool, and **custom firmware** for a
**Harman Kardon AVR 161 / 1610** receiver (STM32F205ZG MCU, Thumb-2), over the LAN.

> Salvage amp, modified at the owner's risk. The stock firmware stays recoverable
> over USB (see "Recovery safety net").

---

## What it does

- **`ampli.py`** — drives the receiver over the network (TCP port 10025, Harman's XML
  protocol): power, volume, mute, source, Bluetooth, and — with the custom firmware —
  **get-status**, **absolute set-volume** and **direct surround-mode selection**.
- **Custom firmware** — adds network commands, pushes state changes to the connected client,
  keeps the amp reachable in sleep, and turns the on-screen menu green so a custom build is
  recognisable at a glance. All by detour + code-cave patching of the stock image.

## Feature status

Features the owner selected during scoping. Everything
targets the STM32 MCU (code caves + detours in the rewritten flash region).

| Feature | Implemented | Validated on hardware |
|---------|:-----------:|:---------------------:|
| `get-status` — real-time volume / mute / source / firmware version / power state | ✅ | ✅ |
| `set-volume` — absolute volume (0–180) | ✅ | ✅ |
| Direct Bluetooth source select | ✅ | ✅ |
| Push state on change (Home Assistant without polling) | ✅ | ✅ volume, source, power, surround mode (0.6–2.5 s after the change); mute is not pushed, see Known issues |
| Green on-screen menu, to tell a custom build from stock | ✅ | ✅ |
| Configurable power-on source + volume | ⬜ planned | — |
| Volume ceiling (max / at power-on) | ⬜ planned | — |
| HDMI-CEC: don't power off when the TV turns off | ⬜ planned | — |
| HDMI-CEC: better power / volume / input sync | ⬜ planned | — |
| Surround mode: read the current mode, select one directly, return to Auto Select¹ | ✅ | ✅ 9 modes accepted on a stereo HDMI source, an impossible mode refused |
| Per-input level trim | ⬜ planned | — |
| Network power-on that always works: the amp stays in sleep instead of turning fully off after an hour | ✅ | ✅ (85 min in sleep, then powered on over the network) |
| ~~Zone 2~~ | ❌ dropped | hardware-impossible (single NJU72340 feeds all channels) |

¹ The native `surround-mode` command only cycles through the mode families (its `para` is
ignored). The stock
firmware already remembers one mode per source; direct selection writes to that same memory.

The network power-on row has one gap: an HDMI-CEC standby order from the TV turns the amp
fully off at once, without going through sleep, so the amp still leaves the network in that case.

## Firmware releases — exact contents

All released images are the stock V002.20 file (6,291,456 bytes) with bytes changed **only**
in the MCU application region: a 4-byte detour and a code cave, plus a few patched
instructions from v1.0.5 on. The resident bootloader
(`< 0x10000`) and the other components in the file (`≥ 0x100000`, DSP etc.) are byte-identical
to stock. Facts below were read back from the published release assets.

| | **v1.0.0** | **v1.0.4** | **v1.0.5** | **v1.1.0** (current) |
|---|---|---|---|---|
| SHA-256 | `b29910b3…0bd4` | `2f0df184…a672` | `d0717fba…9d16` | `da32fb97…723d` |
| Bytes changed vs stock | 618 | 641 | 598 | 1117 |
| Detour | `0x0804F328` (`cmd_dispatch` entry): `b.w 0x080E0180` | same | same | same, plus three patched sites (below) |
| `get-status` | ✅ replies `vol,mute,src,1.0.0` | ✅ replies `vol,mute,src,1.0.4` (same routine, byte-identical) | ✅ replies `vol,mute,src,1.0.5,pwr` — new 5th field: `1` on, `0` in sleep (232-byte routine) | ✅ replies `vol,mute,src,1.1.0,pwr,sur,cat` — 6th field: applied surround mode, 7th: mode family remembered for the source (`0` = Auto Select) |
| `source-selection` + `Bluetooth` | ✅ direct Bluetooth | ✅ same handler, byte-identical | ✅ same handler, byte-identical | ✅ same handler, byte-identical |
| `set-volume` | ❌ **inoperative**: 130-byte routine present (loop of up to 128 re-entrant volume steps) but unreachable — the command string in the image reads `set-volusource-selection`, so the command is passed to the stock dispatcher, which ignores it | ✅ 150-byte single-shot routine, lands exactly on the target | ✅ same routine, byte-identical | ✅ same routine, byte-identical |
| Hardware validation | get-status, Bluetooth | get-status, Bluetooth, set-volume (16/16 targets exact), control port healthy after cold boot | all of v1.0.4, power field (on → sleep → on), 85 min in sleep still reachable then powered on over the network | version after flash, 7-field status, push (volume, source, power, surround), surround selection and refusal, green menu |
| Stays on the network in sleep | ❌ stock: fully off 60 min after going to sleep, network module powered down | ❌ same as stock | ✅ the 3600 s countdown never runs (`beq` → `b` at `0x08010AFE`, one byte) | ✅ same |
| `set-surround` | — | — | — | ✅ `set-surround <code>` selects a surround mode (0–45) if the amp allows it with the current signal; `set-surround auto` returns to Auto Select |
| Push | — | — | — | ✅ the amp sends the `get-status` message by itself when volume, source, power or surround mode changes, for 90 s after the last command received |
| On-screen menu | stock blue | stock blue | stock blue | ✅ green selection bar, titles and borders |

`get-status` reply fields: `vol` is the master volume 0–180 (dB = −80 + 0.5 × vol), `mute` is
0/1, `src` is the firmware's internal source number in decimal, then the custom firmware
version, then (v1.0.5+) the power state, then (v1.1.0+) the surround mode and its family.
**The `mute` field is wrong in every release up to v1.1.0** (see Known issues). Source numbers, each selected and read back on
hardware: 0 Cable Sat, 1 Disc, 2 Media Server / MHL, 3 AUX, 4 Game, 5 STB, 6 Audio, 7 TV, 8 AM,
9 FM, 10 USB, 11 iPod, 12 Home Network, 13 vTuner, 17 Bluetooth.

Without the sleep change, a sleeping amp turns itself fully off after one hour and can then only
be woken with the remote or the front panel (Wake-on-LAN does nothing). With v1.0.5 it stays in
"Device Sleep", keeps answering on port 10025 and accepts `power-on`. The cost is the sleep-mode
power draw, which was not measured.

Cave layout in v1.0.4 and v1.0.5 (offsets from `0x080E0000`): strings `get-status` +0x000, `,` +0x010,
`set-volume` +0x018, `source-selection` +0x024, `Bluetooth` +0x035, version +0x3C0; routines
`emit_status` +0x040 (276 bytes), dispatcher +0x180 (112 bytes, including the relocated 4-byte
prologue and the jump back), `set_volume` +0x280 (150 bytes), Bluetooth handler +0x340
(44 bytes). In v1.0.0 `source-selection` was at +0x020 and `Bluetooth` at +0x032 — the overlap
with `set-volume` (11 bytes at +0x018) is the bug. In v1.0.5 `emit_status` is 232 bytes at the
same +0x040; everything else in the cave is unchanged.

v1.1.0 changes outside the cave: the 1-second tick block at `0x08010AF6` becomes
`bl push_tick ; b 0x08010B40` (6 bytes; it replaces the sleep countdown, which v1.0.5 already
skipped); the `bl memcpy` at `0x080967DC` in the OSD window loader goes through a recolour
routine; two `movs r2,#3` (message-box colours, `0x0809761E` and `0x08097644`) become `#8`.
Cave additions: `emit_status` grows to 276 bytes, dispatcher to 142, version at +0x3C0,
`set-surround` string at +0x3D0, recolour routine at +0x400 (56 bytes), `push_tick` at +0x440
(160 bytes, state kept in unused RAM at `0x2001FF00`), `set_surround` at +0x500 (202 bytes).

Surround mode codes (6th field of `get-status`, `para` of `set-surround`), read from the
firmware's display routine: 0 Virtual Surround, 2/3/5 2CH Stereo, 6 Dolby Digital, 7 DTS,
9 5CH Stereo, 15 Logic 7 Movie, 16 Dolby PLII Movie, 17 DTS Neo:6 Cinema, 21 Logic 7 Music,
22 Dolby PLII Music, 23 DTS Neo:6 Music, 27 Logic 7 Game, 28 Dolby PLII Game, 37–41 Dolby
TrueHD / Digital Plus / DTS-HD, 44 Multi-CH PCM, 45 Harman NSP (full table in
`firmware/re/NOTES.md`). On a 5.1 amp the front panel cycles through Auto Select plus twelve
modes; on hardware, with a stereo HDMI source, 0, 5, 9, 16, 17, 22, 23, 28 and 45 were accepted
and the three Logic 7 modes refused.

v1.0.1, v1.0.2, v1.0.2d, v1.0.3 and the `-test` builds were hardware-test builds and were
never released. The v1.1.0 asset differs from the image validated on hardware
(`1.1.0-test`) only by its version string.

## Repository layout

```
ampli.py                         network control tool (+ get-status / set-volume)
tests/                           client tests (parsing, dB mapping, set-volume logic)
firmware/
  AVR1610_USB(V002_20).fw        STOCK firmware V002.20 (6 MiB) — recovery image
  re/NOTES.md                    the whole reverse engineering (justified addresses)
  re/scripts/                    analysis scripts (capstone / pyghidra) + README
  ghidra/                        annotated Ghidra project
  patches/
    DESIGN-patch1.md             patch #1 design document
    build_patch1.py              builds the patched image (keystone + capstone)
    patchlib.py / verifylib.py   build + static-verification harness
    tests/                       patch tests: static (disassembly) + emulation (emu.py, Unicorn)
    testA-result.md              USB recovery proof (Test A)
    out/                         generated images (git-ignored)
docs/superpowers/
  specs/… plans/…                design & implementation plan
```

## History (what was done)

1. **Discovery & protocol** — amp found on the LAN; port-10025 network protocol (HTTP+XML)
   reverse-engineered and proven by driving the amp (power / volume / mute / source).
2. **Firmware RE** — the `.fw` image analysed (capstone + Ghidra): network dispatcher,
   `build_reply` / `net_send`, state variables (volume / mute / source), source-switch
   functions including `set_src_Bluetooth`.
3. **Updater dissection** — `.fw` format, the IAP flash state machine, layout tables.
   Findings: the image is **unsigned, not checksummed** (written verbatim, each word read back
   after programming; three failed attempts and the updater halts); the MCU is
   **1 MB**; a **code cave at `0x080E0000`** sits in the rewritten region. The resident
   boot-time update path was analysed → USB recovery **without SWD** is possible.
4. **Design & plan** — `DESIGN-patch1.md` (reviewed by a fresh "builder" agent) + a TDD plan.
5. **Harness** — faithful build (byte-identical no-op round-trip) + static verification.
6. **Test A — recovery proof** (on hardware): flashed a network-observable witness, confirmed
   by reading the heart-alive reply's User-Agent (`Harman PATCH1…`), then back to stock
   (`Harman Kardon…`). **The custom-flash ↔ stock-restore cycle is proven over USB.**
7. **First custom features** — get-status, set-volume, direct Bluetooth (detour on `cmd_dispatch` + cave).
   All three are **hardware-validated** (heart-alive intact, `<para>vol,mute,src,fw</para>`).
   The cave code is also exercised by **emulation tests** (Unicorn runs the real patched
   image; `firmware/patches/tests/emu.py`).
8. **Client** — `ampli.py` extended (`status`, `set-volume`, direct `source bluetooth`,
   `surround`).
9. **Sleep, push, surround, OSD** — the 60-minute sleep-to-off timer found and neutralised;
   state pushed from the 1-second tick; the surround selector and the OSD window colours
   located; the MCU ↔ network module dialogue and the whole port-10025 command set decoded.

Full technical detail: `firmware/re/NOTES.md`.

### Known issues

- **v1.0.0 (and test builds up to v1.0.2d): `set-volume` never ran.** A cave layout bug let
  `"source-selection"` overwrite the end of `"set-volume"`, so the command never matched and
  fell through to the stock dispatcher as an unknown command. Fixed in the released v1.0.4
  (first fixed in the unreleased test build v1.0.2); the builder now refuses overlapping cave
  writes.
- **v1.0.3 (never released): dead network service at boot.** Same algorithm as v1.0.4 in a
  larger routine — the first build to occupy cave offsets `+0x320..+0x333`. Port 10025 refused
  connections on three boots; re-flashing v1.0.2 fixed it and the compacted v1.0.4 is healthy.
  **The cause is not understood.** Until it is, a test keeps `set_volume` within the proven
  footprint, and any growth of the cave should be validated on hardware.
- **`mute` is wrong in `get-status`, up to and including v1.1.0.** The field reads the wrong
  flag and always reports `0`, so a mute change is not pushed either. The real flag is known
  and fixed in the builder for the next release. Separately, in the stock firmware `mute-on`,
  `mute-off` and `mute-toggle` all toggle; the next release makes the first two real set-points.
- **One client at a time.** Port 10025 serves a single connection: a new one is accepted and
  the previous one is closed. A pushed message can only reach the last client connected.
- **Requests need their HTTP header**, even though the amp only reads the XML tags: without it
  the amp replays the previous command. A request sent within about 0.1 s of connecting is lost
  half the time; the stock dispatcher ignores a command sent within about 0.5 s of the previous
  one, and keeps only the last of several requests received together.
- **Control port refused after flashing v1.0.5.** On the first boot after the flash, port 10025
  refused connections for 7 minutes (ping fine) after one early connection had succeeded. A
  mains power cycle, then waiting 2.5 minutes before connecting, fixed it and it has been
  healthy since. Not settled: connecting too early during boot, or the first boot after any
  flash. This may also be what was blamed on v1.0.3 above. After flashing or a power cut, wait a
  couple of minutes before the first connection. After flashing v1.1.0 and waiting 2.5 minutes
  the port was healthy. What is now known: the MCU asks the network module to open the port in
  a single timed pass after the IP address is obtained, with no check and no retry, and the same
  pass is replayed on any network (re)connection event.
- The stock dispatcher ignores a command that arrives within roughly half a second of the
  previous handled one (cooldown). `ampli.py` re-sends `set-volume` when that happens.

---

## Flashing

> ⚠️ A flash is irreversible mid-way: **do not cut power** during the ~10 minutes.
> Salvage amp, risk accepted.

### Prepare the USB stick
1. **FAT32** stick, clean root.
2. Copy the image to the root, **named exactly** `AVR1610_USB(V002_20).fw`:
   - **custom** firmware: `firmware/patches/out/AVR1610_patch1_v<version>.fw` (or the release asset)
   - **stock** firmware (recovery): `firmware/AVR1610_USB(V002_20).fw`

   (on macOS: `diskutil eraseDisk FAT32 AVRUPDATE MBRFormat /dev/diskN`, then
   `cp … "/Volumes/AVRUPDATE/AVR1610_USB(V002_20).fw"` and `diskutil eject`.)

### Flash on the amp
1. Amp on, stick in the **front-panel** USB port.
2. **System Setup → Software Update → OK → "SYSTEM UPDATE CONTINUE"**.
3. ~10 min, the amp powers off then back on ("UPGRADE SUCCESS").

### Recovery safety net
The resident bootloader/updater (low 64 KB) is **never rewritten**: a bad app flash stays
recoverable by re-flashing the **stock** image over USB (proven, see Test A). For a patch
that would break early boot (not the case for these network features), keep an **ST-Link SWD**.

---

## Using `ampli.py`

```bash
./ampli.py ping                 # does the amp answer?
./ampli.py on | off | toggle    # power
./ampli.py vol+ [n] | vol- [n]  # relative volume (n steps)
./ampli.py mute [on|off]        # mute
./ampli.py source <name>        # e.g. TV, Disc, "Cable Sat", bluetooth
./ampli.py raw surround-mode    # cycle to the next surround mode (native command)
# --- custom firmware (patch #1) only ---
./ampli.py status               # volume (dB) | mute | source | firmware version
./ampli.py set-volume <0-180>   # absolute volume, single jump (or: set-volume -25db)
./ampli.py source bluetooth     # direct Bluetooth select
```

Amp address: `AMPLI_HOST` environment variable (default `192.168.1.58`).

## Rebuilding the patch

```bash
cd firmware/patches
python3 -m venv .venv && ./.venv/bin/pip install keystone-engine capstone unicorn "setuptools<81" pytest
# (keystone needs its native lib: brew install keystone)
./.venv/bin/python -m pytest -q                     # static + emulation tests
./.venv/bin/python -c "import patchlib; from build_patch1 import build_patch1, FW_VERSION; \
  patchlib.save(build_patch1(patchlib.load_stock(), features={'getstatus','setvolume','bluetooth','keepsleep','push','osdgreen','surround','legacymute'}), f'out/AVR1610_patch1_v{FW_VERSION}.fw')"
```

The patch only adds/changes the rewritten region (`0x10000–0xFFFFF`): a 4-byte detour on
`cmd_dispatch` + a code cave at `0x080E0000`. The image is the **same size, 1:1** with stock.
The build is reproducible: building the `v1.0.4`, `v1.0.5` or `v1.1.0` tag yields the release asset's SHA-256.

---

## Sources

- **Device** — the owner's **Harman Kardon AVR 161**, on the local network (`192.168.1.58`).
  All control and firmware work was proven against this unit.
- **Stock firmware** — `AVR1610_USB(V002_20).fw`, version **V002.20** (April 2015), 6 MiB.
  SHA-256 `0c178d47…8ad5`. Obtained from the community GitHub mirror
  [`github.com/lansinghd/Harman-Kardon_AVR_Firmware`](https://github.com/lansinghd/Harman-Kardon_AVR_Firmware)
  (`AVR_1610/2015-04-15 AVR 1610_USB_V002_20.zip`, byte-identical in size to the local copy).
  Authenticity: the image carries **no vendor signature or checksum**; genuineness was
  cross-checked by internal coherence (valid STM32 vector table, consistent code) **and**
  by the fact that the protocol extracted from it drives the real amp. Confidence it is a
  genuine HK AVR 161/1610 image ≈ 92%; byte-exact identity to the vendor release is not
  independently proven (only one public mirror was found). The firmware's own User-Agent
  string reads `Harman Kardon AVR161/AVR1610`, confirming 161 and 1610 are the same platform.
- **Official Android app ("Harman Kardon Remote")** — the APK was decompiled with
  **androguard** to recover the port-10025 XML protocol and the command set (`CommandSetAvr`):
  command names (`source-selection`, `volume-up`, `mute-on`, `surround-mode`, …) and the
  source `para` values used by `ampli.py`.
- **Firmware reverse engineering** — **Ghidra 12.2** (annotated project in `firmware/ghidra`,
  base `0x08000000`, ARM Cortex-M) plus **capstone** / **pyghidra** scripts in
  `firmware/re/scripts/`. All addresses and findings are documented in `firmware/re/NOTES.md`.
- **Service manual** — the manufacturer's block diagram was used to understand the hardware:
  STM32F205 MCU, CS49834 DSP, SiI9573 HDMI, Milan FS1230A network module, BM840 Bluetooth,
  CS42528 codec, NJU72340 volume/source selector.
- **Live network testing** — the port-10025 protocol, the recovery proof (Test A) and the
  patch validation were all run against the live amp with `ampli.py` / raw sockets.

> Copyright: the stock firmware (`.fw`, `.zip`) and the upgrade instructions (`.doc`) are
> Harman Kardon's property, kept here for personal use in a private repository. If this
> repo is ever made public, remove those files (they are already publicly mirrored at the
> link above) and point to the mirror instead.
