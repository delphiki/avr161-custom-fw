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
| 1  | `get-status` — real-time volume / mute / source | ✅ | ✅ |
| 2  | `set-volume` — absolute volume (0–180) | ✅ firmware¹ | ⏳ in progress |
| 3  | Direct Bluetooth source select | ✅ | ✅ |
| 4  | Push state on change (Home Assistant without polling) | ⬜ planned | — |
| 5  | Configurable power-on source + volume | ⬜ planned | — |
| 6  | Volume ceiling (max / at power-on) | ⬜ planned | — |
| 9  | HDMI-CEC: don't power off when the TV turns off | ⬜ planned | — |
| 10 | HDMI-CEC: better power / volume / input sync | ⬜ planned | — |
| 11 | Surround mode per source / direct selection² | ⬜ planned | — |
| 12 | Per-input level trim | ⬜ planned | — |
| 27 | ~~Zone 2~~ | ❌ dropped | hardware-impossible (single NJU72340 feeds all channels) |

¹ `set-volume` reuses the proven volume-up/down path (re-entrant dispatch). A client-side
fallback (reads `get-status`, steps volume-up/down) is implemented and validated in `ampli.py`.
² A native `surround-mode` command already exists over the API, but it **cycles** modes (the
`para` is ignored). Feature 11 would add reading the current mode and direct selection.

Patch #1 ships features **1, 2, 3**. Remaining selected features: **4, 5, 6, 9, 10, 11, 12**.

## Repository layout

```
ampli.py                         network control tool (+ get-status / set-volume)
tests/                           client tests (parsing, dB mapping)
firmware/
  AVR1610_USB(V002_20).fw        STOCK firmware V002.20 (6 MiB) — recovery image
  re/NOTES.md                    the whole reverse engineering (justified addresses)
  re/scripts/                    analysis scripts (capstone / pyghidra) + README
  ghidra/                        annotated Ghidra project
  patches/
    DESIGN-patch1.md             patch #1 design document
    build_patch1.py              builds the patched image (keystone + capstone)
    patchlib.py / verifylib.py   build + static-verification harness
    tests/                       patch static tests
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
   Findings: the image is **unsigned, not checksummed** (written verbatim); the MCU is
   **1 MB**; a **code cave at `0x080E0000`** sits in the rewritten region. The resident
   boot-time update path was analysed → USB recovery **without SWD** is possible.
4. **Design & plan** — `DESIGN-patch1.md` (reviewed by a fresh "builder" agent) + a TDD plan.
5. **Harness** — faithful build (byte-identical no-op round-trip) + static verification.
6. **Test A — recovery proof** (on hardware): flashed a network-observable witness, confirmed
   by reading the heart-alive reply's User-Agent (`Harman PATCH1…`), then back to stock
   (`Harman Kardon…`). **The custom-flash ↔ stock-restore cycle is proven over USB.**
7. **Patch #1** — get-status, set-volume, direct Bluetooth (detour on `cmd_dispatch` + cave).
   get-status and Bluetooth are **hardware-validated** (heart-alive intact,
   `<para>vol,mute,src</para>`).
8. **Client** — `ampli.py` extended (`status`, `set-volume`, direct `source bluetooth`).

Full technical detail: `firmware/re/NOTES.md`.

---

## Flashing

> ⚠️ A flash is irreversible mid-way: **do not cut power** during the ~10 minutes.
> Salvage amp, risk accepted.

### Prepare the USB stick
1. **FAT32** stick, clean root.
2. Copy the image to the root, **named exactly** `AVR1610_USB(V002_20).fw`:
   - **custom** firmware: `firmware/patches/out/AVR1610_patch1.fw`
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
./ampli.py status               # volume (dB) | mute | source
./ampli.py set-volume <0-180>   # absolute volume  (or: set-volume -25db)
./ampli.py source bluetooth     # direct Bluetooth select
```

Amp address: `AMPLI_HOST` environment variable (default `192.168.1.58`).

## Rebuilding the patch

```bash
cd firmware/patches
python3 -m venv .venv && ./.venv/bin/pip install keystone-engine capstone "setuptools<81" pytest
# (keystone needs its native lib: brew install keystone)
./.venv/bin/python -m pytest -q                     # static tests
./.venv/bin/python -c "import patchlib; from build_patch1 import build_patch1; \
  patchlib.save(build_patch1(patchlib.load_stock(), features={'getstatus','setvolume','bluetooth'}), 'out/AVR1610_patch1.fw')"
```

The patch only adds/changes the rewritten region (`0x10000–0xFFFFF`): a 4-byte detour on
`cmd_dispatch` + a code cave at `0x080E0000`. The image is the **same size, 1:1** with stock.

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
