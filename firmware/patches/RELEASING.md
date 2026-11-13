# Releasing the custom firmware

The **custom firmware has its own version line** (semver), independent of the stock
version (`V002.20`). The version is the single source of truth in `build_patch1.py`
(`FW_VERSION`) and is:

- **embedded in the firmware** — returned as the 4th field of `get-status`
  (`vol,mute,src,<version>,<pwr>,<sur>,<cat>`), so a flashed amp self-identifies over the network
  (`./ampli.py version`);
- used to **name the release artifact** (`AVR1610_patch1_v<version>.fw`);
- used as the **git tag** and **GitHub release** name (`v<version>`).

## Version scheme (semver)

- **MAJOR** — breaking change to the network API or the flash layout.
- **MINOR** — new feature (a new command / behaviour).
- **PATCH** — fix with no feature/API change.

`v1.0.0` = patch #1 (get-status, set-volume, direct Bluetooth).
`v1.0.4` = first version with a working `set-volume` (exact target, single jump). v1.0.1–v1.0.3
were hardware-test builds and were never released.
`v1.0.5` = power state in `get-status`, and the amp no longer leaves the network after an hour
in sleep.
`v1.1.0` = state pushed on change, direct surround-mode selection, green on-screen menu.
`legacymute` in its feature set keeps the (wrong) mute flag of that image so the tag stays
reproducible; drop it, and add `mute`, for the next release.

Before releasing, run the hardware smoke test on a freshly flashed amp: `./ampli.py version`,
`./ampli.py status`, a few `./ampli.py set-volume <n>` in both directions, and confirm the
control port still accepts connections after a cold boot.

## Cut a release

```bash
cd firmware/patches
# 1. bump the version
#    edit build_patch1.py -> FW_VERSION = "1.1.0"

# 2. build + static tests
./.venv/bin/python -m pytest -q
V=$(./.venv/bin/python -c "import build_patch1 as b; print(b.FW_VERSION)")
./.venv/bin/python -c "import patchlib; from build_patch1 import build_patch1, FW_VERSION; \
  patchlib.save(build_patch1(patchlib.load_stock(), features={'getstatus','setvolume','bluetooth','keepsleep','push','osdgreen','surround','legacymute'}), \
  f'out/AVR1610_patch1_v{FW_VERSION}.fw')"

# 3. commit, tag, push
cd ../..
git add -A && git commit -m "release: firmware v$V"
git tag "v$V" && git push origin HEAD --tags

# 4. GitHub release with the firmware artifact
gh release create "v$V" "firmware/patches/out/AVR1610_patch1_v$V.fw" \
  --title "Firmware v$V" --notes "…changelog…"
```

## After flashing, verify

```bash
./ampli.py version        # -> firmware custom v1.1.0
./ampli.py status         # -> … | fw 1.1.0
```

## Recovery

Every release's notes link the **stock** image (`firmware/AVR1610_USB(V002_20).fw`,
`V002.20`) as the recovery firmware. Keep it on hand before flashing a custom build.
