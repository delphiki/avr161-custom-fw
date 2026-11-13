# AVR 161 — network control & custom firmware

Reverse engineering, a network control tool, and **custom firmware** for a
**Harman Kardon AVR 161 / 1610** receiver (STM32F205ZG MCU, Thumb-2), over the LAN.

> Salvage amp, modified at the owner's risk. The stock firmware stays recoverable
> over USB (see "Recovery safety net").

---

## What it does

- **`ampli.py`** — drives the receiver over the network (TCP port 10025, Harman's XML
  protocol): power, volume, mute, source, Bluetooth, surround-mode cycling, and — with
  the custom firmware — **get-status** and **absolute set-volume**.
- **Patch #1** — custom firmware adding network commands via detour + code-cave patching.

## Feature status

Features the owner selected during scoping (numbering kept from that list). Everything
targets the STM32 MCU (code caves + detours in the rewritten flash region).

| # | Feature | Implemented | Validated on hardware |
|---|---------|:-----------:|:---------------------:|
| 1  | `get-status` — real-time volume / mute / source / firmware version | ✅ | ✅ |
| 2  | `set-volume` — absolute volume (0–180) | ✅ | ✅ |
| 3  | Direct Bluetooth source select | ✅ | ✅ |
| 4  | Push state on change (Home Assistant without polling) | ⬜ planned | — |
| 5  | Configurable power-on source + volume | ⬜ planned | — |
| 6  | Volume ceiling (max / at power-on) | ⬜ planned | — |
| 9  | HDMI-CEC: don't power off when the TV turns off | ⬜ planned | — |
| 10 | HDMI-CEC: better power / volume / input sync | ⬜ planned | — |
| 11 | Surround mode per source / direct selection¹ | ⬜ planned | — |
| 12 | Per-input level trim | ⬜ planned | — |
| 28 | Network power-on that always works, whether the amp is in sleep or off | ⬜ planned | — |
| 27 | ~~Zone 2~~ | ❌ dropped | hardware-impossible (single NJU72340 feeds all channels) |

¹ A native `surround-mode` command already exists over the API, but it **cycles** modes (the
`para` is ignored). Feature 11 would add reading the current mode and direct selection.

Patch #1 ships features **1, 2, 3**. Remaining selected features: **4, 5, 6, 9, 10, 11, 12, 28**.

## Firmware releases — exact contents

Both released images are the stock V002.20 file (6,291,456 bytes) with bytes changed **only**
in the MCU application region: a 4-byte detour and a code cave. The resident bootloader
(`< 0x10000`) and the other components in the file (`≥ 0x100000`, DSP etc.) are byte-identical
to stock. Facts below were read back from the published release assets.

| | **v1.0.0** | **v1.0.4** (current) |
|---|---|---|
| SHA-256 | `b29910b3…0bd4` | `2f0df184…a672` |
| Bytes changed vs stock | 618 | 641 |
| Detour | `0x0804F328` (`cmd_dispatch` entry): `b.w 0x080E0180` | same |
| `get-status` | ✅ replies `vol,mute,src,1.0.0` | ✅ replies `vol,mute,src,1.0.4` (same routine, byte-identical) |
| `source-selection` + `Bluetooth` | ✅ direct Bluetooth | ✅ same handler, byte-identical |
| `set-volume` | ❌ **inoperative**: 130-byte routine present (loop of up to 128 re-entrant volume steps) but unreachable — the command string in the image reads `set-volusource-selection`, so the command is passed to the stock dispatcher, which ignores it | ✅ 150-byte single-shot routine, lands exactly on the target |
| Hardware validation | get-status, Bluetooth | get-status, Bluetooth, set-volume (16/16 targets exact), control port healthy after cold boot |

`get-status` reply fields: `vol` is the master volume 0–180 (dB = −80 + 0.5 × vol), `mute` is
0/1, `src` is the firmware's internal source number in decimal (observed: 2 = MHL, 9 = Game,
17 = Bluetooth), then the custom firmware version.

Cave layout in v1.0.4 (offsets from `0x080E0000`): strings `get-status` +0x000, `,` +0x010,
`set-volume` +0x018, `source-selection` +0x024, `Bluetooth` +0x035, version +0x3C0; routines
`emit_status` +0x040 (276 bytes), dispatcher +0x180 (112 bytes, including the relocated 4-byte
prologue and the jump back), `set_volume` +0x280 (150 bytes), Bluetooth handler +0x340
(44 bytes). In v1.0.0 `source-selection` was at +0x020 and `Bluetooth` at +0x032 — the overlap
with `set-volume` (11 bytes at +0x018) is the bug.

v1.0.1, v1.0.2, v1.0.2d and v1.0.3 were hardware-test builds and were never released.

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
7. **Patch #1** — get-status, set-volume, direct Bluetooth (detour on `cmd_dispatch` + cave).
   All three are **hardware-validated** (heart-alive intact, `<para>vol,mute,src,fw</para>`).
   The cave code is also exercised by **emulation tests** (Unicorn runs the real patched
   image; `firmware/patches/tests/emu.py`).
8. **Client** — `ampli.py` extended (`status`, `set-volume`, direct `source bluetooth`).

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
  patchlib.save(build_patch1(patchlib.load_stock(), features={'getstatus','setvolume','bluetooth'}), f'out/AVR1610_patch1_v{FW_VERSION}.fw')"
```

The patch only adds/changes the rewritten region (`0x10000–0xFFFFF`): a 4-byte detour on
`cmd_dispatch` + a code cave at `0x080E0000`. The image is the **same size, 1:1** with stock.
The build is reproducible: building the `v1.0.4` tag yields the release asset's SHA-256.

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
