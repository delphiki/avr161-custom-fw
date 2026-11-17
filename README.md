# Harman Kardon AVR 161 — custom firmware & network control

Custom firmware for the **Harman Kardon AVR 161 / AVR 1610** receiver, and a small
command-line tool to drive it over the local network.

The custom firmware is the stock firmware (V002.20) with a few additions. It is installed
from a USB stick, like an official update, and the stock firmware can be put back the same way.

> ## ⚠️ Disclaimer — use at your own risk
>
> This is an unofficial, hobby project. It is **not** affiliated with, endorsed by, or supported
> by Harman Kardon.
>
> Flashing modified firmware can **permanently damage your receiver** ("brick" it), will most
> likely **void any warranty**, and may cause it to behave in unexpected ways. It has been
> tested on **one single unit**. Nothing guarantees it works on yours.
>
> Everything here is provided **"as is", without warranty of any kind**. **You alone are
> responsible** for what you do with it. The author accepts **no liability** for any damage,
> data loss, malfunction or other consequence resulting from the use of this firmware, these
> tools or this documentation.
>
> If you are not comfortable with the idea of losing the device, do not flash it.

---

## What the custom firmware changes

Everything the stock firmware does keeps working. The custom firmware adds:

- **Read the amp's state over the network** — a `get-status` command returns the volume,
  mute, source, firmware version, power state and surround mode. The stock firmware has no
  way to ask the amp what it is doing.
- **State changes are pushed** — when the volume, mute, source, power state or surround mode
  changes (remote, front panel, HDMI…), the amp tells the connected client by itself.
- **Absolute volume** — `set-volume` jumps straight to a given level, instead of stepping up
  or down.
- **Direct Bluetooth** — the Bluetooth source can be selected over the network.
- **Direct surround mode selection** — pick a surround mode, or go back to "Auto Select".
  The stock command only cycles to the next mode.
- **Mute on / mute off really set the state.** In the stock firmware both simply toggle.
- **The amp stays reachable when it is off.** The stock firmware turns the network module off
  one hour after going to sleep, and after that only the remote can wake the amp. The custom
  firmware keeps the network module powered, so the amp can always be **turned on over the
  network**.
  - `power-off` puts the amp to sleep; `power-full-off` turns it off but keeps it reachable.
  - `power-full-off deep` is the stock power-down (network off, lowest consumption). Only the
    remote or the front panel can turn the amp back on from there.
- **Three power states are reported** — on, sleep, off.
- **Green on-screen menu** — the menu is green instead of blue, so you can tell at a glance
  that the custom firmware is installed.

Nothing else is modified: the bootloader, the DSP and the other components in the firmware
file are byte-identical to stock.

### Good to know

- Staying reachable has a cost: the network module stays powered when the amp is off. The
  extra consumption was not measured. Use `power-full-off deep` if you want the stock behaviour.
- The amp accepts **one network client at a time**.
- After plugging the amp back into mains, give it about a minute before it answers on the
  network.
- An HDMI-CEC standby order from the TV has not been tested with this version.

---

## Installing

Download the latest `AVR1610_patch1_v<version>.fw` from the
[releases](../../releases), or build it yourself (see below).

> **Do not cut the power during the update** (about 10 minutes).

1. Format a USB stick as **FAT32** and make sure it is empty.
2. Copy the firmware file to the root of the stick and rename it **exactly**
   `AVR1610_USB(V002_20).fw`.
3. Turn the amp on and plug the stick into the **front** USB port.
4. On the amp: **System Setup → Software Update → OK → "SYSTEM UPDATE CONTINUE"**.
5. Wait about 10 minutes. The amp turns off and on again by itself ("UPGRADE SUCCESS").
6. Remove the stick.

To check: the on-screen menu is green, and `./ampli.py version` prints the version.

On macOS, steps 1–2 look like this:

```bash
diskutil eraseDisk FAT32 AVRUPDATE MBRFormat /dev/diskN      # N = your stick!
cp AVR1610_patch1_v1.2.0.fw "/Volumes/AVRUPDATE/AVR1610_USB(V002_20).fw"
diskutil eject /Volumes/AVRUPDATE
```

### Going back to the stock firmware

Do exactly the same with the **stock** file, `firmware/AVR1610_USB(V002_20).fw`. The part of
the amp that performs the update is never modified by the custom firmware, so this keeps
working even if a custom build misbehaves. Keep that file at hand before flashing anything.

---

## Controlling the amp: `ampli.py`

`ampli.py` needs only Python 3. Set the amp's address with the `AMPLI_HOST` environment
variable.

```bash
export AMPLI_HOST=192.168.1.58

./ampli.py ping                  # does the amp answer?
./ampli.py on | off | toggle     # power (off = sleep)
./ampli.py vol+ [n] | vol- [n]   # volume up / down by n steps
./ampli.py mute [on|off]         # mute
./ampli.py source <name>         # TV, Disc, "Cable Sat", Bluetooth…
./ampli.py raw <command> [para]  # any raw command, e.g. raw power-full-off deep

# with the custom firmware
./ampli.py status                # power | volume | mute | source | surround | version
./ampli.py set-volume <0-180>    # absolute volume (or in dB: set-volume -25db)
./ampli.py surround [mode]       # show the surround mode, or select one ("auto" = Auto Select)
./ampli.py version               # custom firmware version
```

The amp talks HTTP + XML on TCP port 10025. If you want to write your own client, the
protocol and every command are described in `firmware/re/NOTES.md`.

---

## Building the firmware yourself

```bash
cd firmware/patches
python3 -m venv .venv
./.venv/bin/pip install keystone-engine capstone unicorn "setuptools<81" pytest
# keystone needs its native library: brew install keystone

./.venv/bin/python -m pytest -q        # tests (the patched code runs in an emulator)
./.venv/bin/python -c "import patchlib; from build_patch1 import build_patch1, FW_VERSION; \
  patchlib.save(build_patch1(patchlib.load_stock(), features={'getstatus','setvolume','bluetooth','keepsleep','push','osdgreen','surround','netoff','mute','sleeptimer','portguard','powerstate'}), f'out/AVR1610_patch1_v{FW_VERSION}.fw')"
```

The build is reproducible: it produces the same file, byte for byte, as the release.
Release procedure: `firmware/patches/RELEASING.md`.

## How it works, in short

The receiver's main processor is an STM32F205. Its firmware is neither signed nor checksummed,
and an unused area of its flash memory is rewritten by every update. The custom firmware puts
its extra code in that unused area and redirects a handful of instructions of the stock code
to it. The file keeps the exact size and layout of the stock one.

For the full story — the reverse engineering, every address, the hardware tests and the dead
ends — see `firmware/re/NOTES.md` (in French).

## Repository layout

```
ampli.py                     network control tool
tests/                       tests for ampli.py
firmware/
  AVR1610_USB(V002_20).fw    STOCK firmware V002.20 — the recovery image
  patches/                   builds the custom firmware (build_patch1.py) and its tests
  re/                        reverse-engineering notes and scripts
  ghidra/                    annotated Ghidra project
```

## Credits and copyright

- The stock firmware comes from the community mirror
  [`lansinghd/Harman-Kardon_AVR_Firmware`](https://github.com/lansinghd/Harman-Kardon_AVR_Firmware).
- The network protocol was recovered from the official "Harman Kardon Remote" Android app and
  from the firmware itself.

The stock firmware (`.fw`, `.zip`) and the upgrade instructions (`.doc`) are Harman Kardon's
property, kept here for personal use in a private repository. If this repository is ever made
public, remove those files and point to the mirror above instead.
