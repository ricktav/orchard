# J81 review, board matrix, and next work

Review of ricktav's work as it lives on **upstream** `OrchardLinux/orchard` `main` (commit `5d0c610`, Release 0.3.3), not the fork's lagging `main`. Live page fetched 2026-11-23:

https://github.com/OrchardLinux/orchard/blob/main/docs/compatibility.md

That file is **byte-identical** to this checkout's `docs/compatibility.md` (325 lines). Feature states in the live Features table match every `devices/*/device.toml` `[features]` block (0 mismatches).

Rick's DCO line, as requested by henrikklee on #195 and authorised for this branch:

`Signed-off-by: ricktav <82380971+ricktav@users.noreply.github.com>`

This branch records that sign-off on the four #197 / #195 patches (they had none). No other code changes. No PR or comment was opened on OrchardLinux/orchard.

---

## Method

- Read the merged series: #185 / #188 (ANS1 storage), #192 (speakers), #193 (BT status), #194 (sleep status), #195 (3 Mbit/s UART), #197 (D2207 charging), plus later ricktav patches still on `main` (J85, N66, and shared driver match-data).
- Cross-checked `devices/j81/device.toml`, `t7001-air2.dtsi` patches, `tools/catalog/drivers.json`, CHANGELOG 0.3.3, and the live compatibility page.
- Applied the apple-4k patch series with `kernel/audit-patches.py /tmp/linux-orchard --device j81` against pinned `v7.3-rc1` (`cee9395`). **PASS** — 284 files, OF match strings retained, DART window contract retained.
- Full `Image.gz` compile was **not feasible** here: no Podman, no aarch64 sysroot, host clang-18 is x86. Config already has `CONFIG_APPLE_ASP=m`, `CONFIG_SND_SOC_MAX98721=m`, `CONFIG_SND_AUDIO_GRAPH_CARD2=m`, `CONFIG_APPLE_TRISTAR_CHARGER=y`, `CONFIG_APPLE_SIO=m` on apple-4k.

---

## Task 1 — findings (severity-ranked)

Line numbers are in the **patch files** as they sit on upstream `main` (and this branch, after the SoB addition).

### High

**H1. ANS1 teardown writes the CPU-start *bit* as an MMIO offset, so it never stops the coprocessor.**

`kernel/patches/drivers/block/0002-block-Add-a-driver-for-the-Apple-ANS1-storage-contro.patch`

```
#define AKF_V1_REMAP_IOP_LO     0x10
#define AKF_V1_CPU_CONTROL      0x28
#define AKF_V1_CPU_CONTROL_START BIT(4)   /* = 0x10 */
```

Start is correct (patch ~1106): `writel(AKF_V1_CPU_CONTROL_START, asp->akf_base + AKF_V1_CPU_CONTROL)`.

Probe-fail and `remove()` (~1342 and ~1370) do `writel(0, asp->akf_base + AKF_V1_CPU_CONTROL_START)`, i.e. write 0 to **offset 0x10** (`AKF_V1_REMAP_IOP_LO`), which start already programmed to 0. The ANS CPU at 0x28 is left running after failed probe, module unload, or shutdown.

J81 boots and installs, so the start path is fine. This is a teardown / failed-probe bug, not a boot blocker. Fix is `writel(0, asp->akf_base + AKF_V1_CPU_CONTROL)` (clear bit 4 only if other bits matter). Needs a J81/J72 storage reboot test; not applied here.

Authorship is Nick Chan with ricktav SoB (#188). `0004` later fixed `kmalloc_obj` NULL vs `IS_ERR` and the tag-set timeout unit; it did **not** fix this writel.

**H2. Charging and 3 Mbit/s patches shipped without Signed-off-by (Henrik's merge request).**

On `main` as merged, these four had `From: ricktav` and `Co-Authored-By: Claude Opus 5.5` but no `Signed-off-by`:

| Patch | PR |
| --- | --- |
| `kernel/patches/drivers/power/0042-dt-bindings-power-supply-apple-tristar-charger-Add-t.patch` | #197 |
| `kernel/patches/drivers/power/0043-power-supply-apple_tristar_charger-Support-the-D2207.patch` | #197 |
| `kernel/patches/devices/t7001/0018-arm64-dts-apple-t7001-air2-Add-Lightning-charging.patch` | #197 |
| `kernel/patches/devices/t7001/0019-arm64-dts-apple-t7001-air2-Run-Bluetooth-at-3-Mbit-s.patch` | #195 |

henrikklee asked for this on #195 (22 Nov 2026). **Fixed on this branch** with the SoB line above. Nineteen other ricktav-authored patches on `main` still lack it (see L4).

### Medium

**M1. D2207 charging is conservative on unknown sources, but two current-limit paths are untested and the plug IRQ is deliberately omitted.**

What looks right (shared `apple_tristar_charger`, not rewritten for J81):

- Unknown / mux-busy sources stay at the **500 mA** USB 2.0 fallback (`TRISTAR_CHG_FALLBACK_CODE`).
- Grants above fallback only if the pack is 5–40 °C, 3.2–4.35 V, and battery current within ±3 A (`tristar_pack_allows_grant` in `0003`, ~290). That thermal/voltage window applies to D2207 too.
- iBoot's 100 mA is never adopted as a “known” grant; a higher hardware value the driver cannot explain drops to fallback (`0043` ~296).
- Encoding `mA = code × 12.5 + 75` is shared; J81 DT `input-current-limit-microamp = <2400000>` matches the ADT `usb-input-limit-max` 0x960.
- D2207 addresses match the #197 table (connection 0x60, status 0x62, limit 0x4c0, ADC 0x500/0x502). Match data keeps `apple,tristar-charger` as D2365, so J71b/J71t do not change.
- DCP keeps USB data off (`0039`); J81 tested CDP (Mac) and an Apple USB-C adapter at 1500 mA.

Caveats:

- **Apple USB-A wall brick (BrickID) was not tested** (#197 “Not included”). The brick table can grant up to the 2400 mA board max. Untested high-current path.
- **No plug/source IRQs on J81** (`0018` ~65–73; `0042` makes `interrupts` minItems 2). Documented: event 0 stays unmasked across a Linux→DFU reset and froze 4–5 of 5 RAM boots. Installed `orchard launch` was fine. Detection is the 100 ms poll of 0x60. Sleep with cable in was tested (grant returns). Residual risk: a source that changes advertisement without a connection-state change is noticed more slowly than on J71b.
- D2207 `0x10` bit 2 (“input disable” below 75 mA) is unused. Fine at current grants.
- `CONFIG_APPLE_TRISTAR_ACCESSORY` is **off** on apple-4k. Lightning accessories are out of scope.

**M2. `#define DEBUG 1` in `asp.c` (0002 ~79).** Forces debug prints in every apple-4k/16k ANS1 build. Distro kernels and mainline will reject this. Easy delete after a log-level pass.

**M3. MAX98721 thermal / overcurrent IRQ is implemented in the driver and omitted from the DT.**

`0023` ~395–414 logs FLAG0–2 if `i2c->irq` is set. `0017` ~15–16 and ~36–39 leave GPIO 8/9 and “function-alive” GPIO 101 undescribed. ALC limiter and -12 dB MCA clamp (`t7001_mca_hw.attenuation = 4`) are the only speaker protection. iOS uses IV-sense ADCs for excursion/thermal; this driver leaves them off on purpose. Safe for bring-up, not for unattended loud playback at UCM gain 22.

**M4. `bluetooth_audio = working` is A2DP (and CVSD), not wideband HFP.**

#195: mSBC SCO opens and stays silent; PipeWire prefers mSBC so a call needs “Headset Head Unit (CVSD)” by hand. Glance “Bluetooth ✅” and Features `bluetooth_audio working` are still fair for headphones + HID. A changelog/footnote would help users.

**M5. RTKit `epmap_done` lets a client start app endpoints before `apple_rtkit_is_running()` (`soc-apple/0027`).** Required for ANS1. Footgun for GPU/AOP clients. Mainline needs a narrower flag, not a global bypass.

**M6. Mainline blockers for this series (not Orchard bugs).**

| Piece | Why it will not go upstream as-is |
| --- | --- |
| `asp.c` ANS1 | Custom (non-NVMe) protocol, `DEBUG 1`, wrong CPU-stop writel, dual `GPL-2.0 OR MIT`, writable user area by default |
| `max98721.c` | No public datasheet; register map copied from MAX98925 + iOS `AppleMAX98721Amp` |
| D2207 charger | Reverse-engineered PMIC addresses from `AppleD2207PMU` |
| Almost every ricktav patch | `Co-Authored-By: Claude Opus 5.5`; several also `Assisted-by: LLM` |
| MCA v1 / NCO stride / SIO V1 | Reasonable incremental Apple SoC work **after** a hardware-log respin; `0021` commit text still says “Compile-tested only” |

The **audio-graph-card2** refcount fix (`sound/0027`) is the one piece that should be sent to ASoC on its own. It is generic, tested on a semi-multi link, and matches `graph_get_next_multi_ep()` dropping the port it is given.

### Low

**L1. Nineteen other ricktav patches on `main` still have no Signed-off-by.** Henrik only asked for #197/#195. Remaining: J85 touch/Wi-Fi/SPI (`s5l8960x/0003–0004`, `input/0032–0033`, `spi/0011`, `usb/0021`, `wifi/0012`), N66 storage/touch/ALS (`s8000/0019–0023`, `pci/0041–0043`, `input/0036–0037`, `regulator/0011–0012`). Same SoB line would cover them.

**L2. Kernel style nits**

- `0043` ~181: comment line well over 80 columns (“The charger status 0x18a is not presence. Its bits describe”).
- `asp.c` comment typos “alighed”, “constrianted”; `void *__iomem akf_base` should be `void __iomem *`.
- `0013` (I2C1 enable) still says amplifiers have no driver; superseded by `0017`.
- `max98721_amp_event` ignores `regmap_write` errors on enable/disable (`0023` ~214–228).
- `REGCACHE_MAPLE` on an 8-bit codec map is unusual (MAX98925 uses FLAT / none).
- TLV comment “1 is -6 dB” vs `DECLARE_TLV_DB_SCALE(..., -700, 100, 1)` (−7 dB at the first non-mute step). UCM still sets 22, the iOS cap.

**L3. J82 (Air 2 Cellular) has the same DT binds as J81 and is all `untested`.** Correct per CONTRIBUTING (working only after seen on the device). Henrik already copied speakers + charging onto J82 (`c33d435`). Highest-value *test*, not a code bug.

### What looks correct (keep)

- Speakers: iOS-faithful MAX98721 init, mute-at-probe, gain cap `0x16`, ALC on, DAPM 1.5 ms / 9 ms, TDM `<0 1>` as ASoC per-slot boolean mask (slot 1), MCA ÷4, UCM `J81 Speakers` / `Orchard/ipad-air2`.
- SIO V1: remap/CPU/mailbox offsets match ANS1; `enable_tx` fixes the −EBUSY ready reply.
- NCO T7001: 0x1000 stride, 342857142 Hz reference from live ADT.
- Bluetooth `max-speed = <3000000>` matches ADT `transport-speed`; UART 24 MHz ÷ 8.
- Storage: user area writable (Orchard policy vs NixOS read-only); aux namespaces read-only.
- CHANGELOG 0.3.3 J81 bullets match toml: install, speakers (not jack/mic), 1.5 A charging, sleep, BT at 3 Mbit/s.
- `devices/j81/firmware.json` stages `t7000-smartio.bin` via `smartio-from-kernelcache@2`.
- apple-4k and apple-16k both got `CONFIG_SND_AUDIO_GRAPH_CARD2=m` and `CONFIG_SND_SOC_MAX98721=m`.

---

## Task 2 — feature matrix

Legend: **W** working · **U** untested (driver/DT exists) · **M** missing · **N** no such hardware.

Columns follow `features.toml`: display, screen_off, backlight, gpu_desktop, touch, buttons, accelerometer, gyroscope, light_sensor, touch_id, storage_read, storage_write, wifi, bluetooth_input, bluetooth_audio, cellular, battery, charging, charging_control, suspend, resume, usb_serial, usb_network, usb_host, audio_output, audio_input, camera, video_decode_hevc.

Source: `devices/*/device.toml` on upstream `main`. The live Features table matches this exactly.

| Board | Product | Plat | St | Tested | dsp | soff | bl | gpu | tch | btn | acc | gyr | lux | tid | sr | sw | wifi | bti | bta | cell | bat | chg | chgc | sus | res | us | un | uh | ao | ai | cam | hevc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `p105` | iPad mini 1 (Wi-Fi) | armv7 | exp | shaynelegault | U | U | U | M | U | U | M | M | M | M | W | U | U | U | U | N | U | U | U | M | M | U | U | M | U | M | M | M |
| `j1` | iPad 3 (Wi-Fi) | armv7 | exp | – | U | M | M | M | U | M | M | M | M | N | M | M | U | M | M | N | M | M | M | M | M | U | U | M | M | M | M | M |
| `j71` | iPad Air (Wi-Fi) | 4k | exp | – | U | M | U | M | U | U | M | M | M | M | U | U | U | M | M | M | U | U | U | U | U | U | U | M | U | M | M | M |
| `j72` | iPad Air (Cellular) | 4k | exp | thisiscamk | W | U | W | M | W | W | M | M | M | N | W | W | U | M | M | M | U | U | U | U | U | W | W | M | U | M | M | M |
| `j73` | iPad Air (China) | 4k | exp | – | U | M | U | M | U | U | M | M | M | M | U | U | U | M | M | M | U | U | U | U | U | U | U | M | U | M | M | M |
| `j85` | iPad mini 2 (Wi-Fi) | 4k | exp | ricktav | U | M | U | M | W | U | M | M | M | M | U | U | W | M | M | M | U | U | U | U | U | U | U | M | M | M | M | M |
| `j85m` | iPad mini 3 (Wi-Fi) | 4k | exp | – | U | M | U | M | U | U | M | M | M | M | U | U | M | M | M | M | U | U | U | U | U | U | U | M | M | M | M | M |
| `j86` | iPad mini 2 (Cellular) | 4k | exp | – | U | M | U | M | U | U | M | M | M | M | U | U | U | M | M | M | U | U | U | U | U | U | U | M | M | M | M | M |
| `j86m` | iPad mini 3 (Cellular) | 4k | exp | – | U | M | U | M | U | U | M | M | M | M | U | U | M | M | M | M | U | U | U | U | U | U | U | M | M | M | M | M |
| `j87` | iPad mini 2 (China) | 4k | exp | – | U | M | U | M | U | U | M | M | M | M | U | U | U | M | M | M | U | U | U | U | U | U | U | M | M | M | M | M |
| `j87m` | iPad mini 3 (China) | 4k | exp | – | U | M | U | M | U | U | M | M | M | M | U | U | M | M | M | M | U | U | U | U | U | U | U | M | M | M | M | M |
| `n51` | iPhone 5s (GSM) | 4k | exp | – | U | M | U | M | M | U | M | M | M | M | U | U | M | M | M | M | M | M | M | U | U | U | U | M | M | M | M | M |
| `n53` | iPhone 5s (Global) | 4k | exp | – | U | M | U | M | M | U | M | M | M | M | U | U | M | M | M | M | M | M | M | U | U | U | U | M | M | M | M | M |
| `j96` | iPad mini 4 (Wi-Fi) | 4k | exp | tcballard | W | U | W | U | U | W | M | M | M | M | U | U | W | M | M | N | W | M | M | U | U | W | W | M | M | M | M | M |
| `j97` | iPad mini 4 (Cellular) | 4k | exp | – | U | U | U | U | U | U | M | M | M | M | U | U | U | M | M | M | U | M | M | U | U | U | U | M | M | M | M | M |
| `n102` | iPod touch 6 | 4k | exp | brkosebay | W | U | W | W | W | W | M | M | M | N | W | W | W | U | U | N | M | M | M | U | U | W | U | M | M | M | M | M |
| `n56` | iPhone 6+ | 4k | exp | – | U | U | U | U | M | U | M | M | M | M | U | U | U | U | U | M | U | M | M | U | U | U | U | M | M | M | M | M |
| `n61` | iPhone 6 | 4k | exp | amethyst-oak | W | U | U | U | W | U | M | M | M | M | U | U | U | U | U | M | U | M | M | U | U | W | U | M | M | M | M | M |
| `j81` | iPad Air 2 (Wi-Fi) | 4k | exp | ricktav, mattonik | W | W | W | M | W | W | M | M | M | M | W | W | W | W | W | N | W | W | W | W | W | W | W | M | W | M | M | M |
| `j82` | iPad Air 2 (Cellular) | 4k | exp | – | U | U | U | M | U | U | M | M | M | M | U | U | U | U | U | M | U | U | U | U | U | U | U | M | U | M | M | M |
| `j71s` | iPad 5 (Wi-Fi, Samsung) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | U | U | U | N | U | U | U | U | U | U | U | U | U | U | M | U |
| `j72s` | iPad 5 (Cellular, Samsung) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | U | U | U | M | U | U | U | U | U | U | U | U | U | U | M | U |
| `j71t` | iPad 5 (Wi-Fi, TSMC) | 16k | exp | brkosebay | W | W | W | W | W | W | W | W | W | M | W | W | W | W | U | N | W | W | W | W | W | W | W | W | W | W | M | W |
| `j72t` | iPad 5 (Cellular, TSMC) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | U | U | U | M | U | U | U | U | U | U | U | U | U | U | M | U |
| `n66` | iPhone 6s Plus (S8000) | 16k | exp | ricktav | W | U | W | U | W | W | U | U | W | M | W | W | M | M | M | M | U | U | M | U | U | U | U | M | M | M | M | U |
| `n66m` | iPhone 6s Plus (S8003) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | M | M | M | M | U | U | M | U | U | U | U | M | M | M | M | U |
| `n69u` | iPhone SE (S8000) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | M | M | M | M | U | U | M | U | U | U | U | M | M | M | M | U |
| `n69` | iPhone SE (S8003) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | M | M | M | M | U | U | M | U | U | U | U | M | M | M | M | U |
| `n71` | iPhone 6s (S8000) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | M | M | M | M | U | U | M | U | U | U | U | M | M | M | M | U |
| `n71m` | iPhone 6s (S8003) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | M | M | M | M | U | U | M | U | U | U | U | M | M | M | M | U |
| `j127` `j128` `j98a` `j99a` | iPad Pro 9.7 / 12.9 A9X | 16k | exp | – | U | M | U | M | M | U | M | M | M | M | M | M | M | M | M | M | M | M | M | U | U | U | U | M | M | M | M | M |
| `d10` `d101` `d11` `d111` | iPhone 7 / 7 Plus | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | U | U | U | M | U | U | M | U | U | U | U | M | M | M | M | U |
| `j171` | iPad 7 (Wi-Fi) | 16k | exp | jerricky26 | W | W | W | W | W | W | W | W | W | M | W | W | W | W | W | N | W | W | U | W | W | W | W | U | W | W | M | W |
| `j172` | iPad 7 (Cellular) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | U | U | U | M | U | U | U | U | U | U | U | U | U | U | M | U |
| `j71b` | iPad 6 (Wi-Fi) | 16k | **sup** | henrikklee, stuart902, dl-alexandre, tiktop101 | W | W | W | W | W | W | W | U | U | M | W | W | W | W | W | N | W | W | W | W | W | W | W | U | W | W | M | U |
| `j72b` | iPad 6 (Cellular) | 16k | exp | – | U | U | U | U | U | U | U | U | U | M | U | U | U | U | U | M | U | U | U | U | U | U | U | U | U | U | M | U |
| `j120` `j121` `j207` `j208` | iPad Pro A10X | 16k | exp | – | U | M | U | M | M | U | M | M | M | M | M | M | M | M | M | M | M | M | M | U | U | U | U | M | M | M | M | M |
| `d20` `d201` `d211` | iPhone 8 | 16k | exp | – | U | U | U | M | M | U | M | M | M | M | U | U | U | M | M | M | U | M | M | U | U | U | U | M | M | M | M | M |
| `d21` | iPhone 8 Plus (Global) | 16k | exp | ryzensnyper | U | U | U | M | U | U | M | M | M | M | U | U | U | M | M | M | U | M | M | U | U | U | U | M | M | M | M | M |
| `d22` | iPhone X (Global) | 16k | exp | – | U | U | U | M | U | U | M | M | M | M | U | U | U | M | M | M | U | M | M | U | U | U | U | M | M | M | M | M |
| `d221` | iPhone X (GSM) | 16k | exp | edulmartins | W | W | W | M | W | W | M | M | M | N | W | W | U | M | M | M | W | M | M | U | U | W | U | M | M | M | M | M |

Working-feature counts: `j71t` 24 · `j171` 23 · `j71b` 21 · `j81` 18 · `n102` / `d221` 9 · `j72` 8 · `j96` / `n66` 7.

44 further boards are `known` only (A5–A6X catalog, all A12–A13). Orchard does not build for them.

### J81 vs J71b (the supported A10 reference)

| Feature | J71b | J81 | Gap |
| --- | --- | --- | --- |
| Daily tablet stack (display, touch, Wi-Fi, BT, speakers, charge, sleep, USB gadget) | W | W | Parity |
| gpu_desktop | W | M | A8X GPU: DWI always-on so core ID reads `0x00070500`; no Zink/desktop yet |
| accelerometer / rotation | W | M | No AOP/motion on t7001 |
| gyroscope, light_sensor | U | M | Same |
| audio_input | W (PDM) | M | CS42L81 / MCA0 not described |
| video_decode_hevc | U | M | No VXD on A8X in tree |
| usb_host | U | M | No Tristar host path |
| camera, touch_id | M | M | Same class |

---

## compatibility.md discrepancies

Live page: https://github.com/OrchardLinux/orchard/blob/main/docs/compatibility.md  
Checkout: `docs/compatibility.md` at `5d0c610`  
Result: **identical**.

Cross-check of every experimental/supported board:

| Layer | vs code / DT / toml | Result |
| --- | --- | --- |
| Features table (live) vs `devices/*/device.toml` | Every cell | **Agree** (0 mismatches) |
| Glance “Does my device work?” vs toml | Projection: GPU←gpu_desktop, Sound←audio_output, Charges←charging, Sleep←suspend, Rotation←accelerometer, Bluetooth←input/audio, Installs←install blockers | **Agree** for J81 and the other glance rows checked (J71b, J171, J82, J85, J96, N66, N102, D221) |
| Drivers table vs `tools/catalog/drivers.json` | Bind scan of apple-4k/16k DTBs | **Agree** (generated together) |
| Drivers vs toml | Catalog’s own “Where feature states and drivers disagree” | Listed below; these are real doc/code splits |

### Catalog’s published disagreements (live page § “Where feature states and drivers disagree”)

These are in the live page on purpose. They are **toml vs DTB bind**, not live-vs-checkout drift.

| Board | Feature | Live toml state | DT bind | Notes |
| --- | --- | --- | --- | --- |
| `j71` `j72` `j73` | Wi-Fi | untested | no | `feature-drivers.toml` only looks for `pci_pwrctrl_apple_wifi`. A7 Wi-Fi is HSIC (`apple-a7-wlan`), so the catalog cannot see it. |
| `j85` | Wi-Fi | **working** | no | Same HSIC gap. Rick tested RAM-boot Wi-Fi on J85. Glance still shows ✅, which matches toml, not the Drivers column. |
| `j86` `j87` | Wi-Fi | untested | no | Same HSIC gap. |
| `j85` `j85m` `j86` `j86m` `j87` `j87m` | Speakers | **missing** | **yes** | A7 MCA speaker nodes are on in `s5l8960x` patches. Toml says they do not work (mini 2/3 may not share the Air’s amps). Drivers table over-claims. |
| `n51` `n53` | Speakers | missing | yes | iPhone 5s: speaker node from the A7 enablement; no phone speaker bring-up. |
| `j71s` `j72s` `j72t` | Microphone | untested | no | `audio_input` is keyed only to `snd_soc_apple_t8010_pdm`. A9 mics are AOP/PDM-shaped and do not hit that name. |
| `j71t` | Microphone | **working** | no | Same catalog key. Toml is right (tested); Drivers column is blind. |

Extra binds the live page does **not** list (armv7 / incomplete kernel scan): `j1` touch/Wi-Fi/USB untested with no apple-16k/4k bind; `p105` many untested/working cells with no bind in `drivers.json` (Cascadia armv7, not in the 4k/16k catalog).

### J81: live page vs DT / drivers (no state error)

`tools/catalog/drivers.json` `j81` binds: audio_output, backlight, battery, bluetooth_audio, bluetooth_input, buttons, charging, storage_read, storage_write, touch, usb_network, usb_serial, wifi.

That matches every J81 **W** feature that the catalog knows how to see. Features the catalog does not scan (display, screen_off, gpu_desktop, sensors, charging_control, suspend, resume, usb_host, audio_input, camera, hevc) are consistent with toml: gpu/sensors/mic/camera/hevc **M**, suspend/resume **W** from #194 (no extra DT).

`j82` binds are **identical** to `j81`. Live glance shows J82 all 🤔, Features all untested. That is the CONTRIBUTING rule (not tested on the cellular Air 2), not a missing port. Code is already shared via `t7001-air2.dtsi`.

Semantic caveats the glance table cannot show (J81):

| Glance cell | Live | What the code actually does |
| --- | --- | --- |
| Sound ✅ | speakers | Headphone jack (CS42L81 on SPI1 / MCA0) and mics are **not** supported. Toml comment already says this; glance does not. |
| Bluetooth ✅ | HID + A2DP | mSBC HFP is silent; CVSD works if the profile is picked by hand. |
| Charges ✅ | 1.5 A on CDP / Apple USB-C | USB-A BrickID path untested; DT allows 2.4 A. |
| GPU ❌ | missing | DWI always-on (`t7001/0012`); GPU core ID already reads. Desktop/Zink is the remaining work, not “GPU silicon dead”. |
| Rotation ❌ | accel missing | Correct. Smart Cover wake exists (`0008`/`0009`) but is not rotation. |

### Proposed corrected rows for J81

Do **not** change the Features-table states. They match hardware tests in #192–#197. Propose footnotes / glance notes, and one Drivers-table clarification.

**Glance (live today):**

```
| iPad Air 2 (Wi-Fi) | A8X | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ricktav, mattonik |
```

**Proposed glance + notes (same symbols, explicit limits):**

```
| iPad Air 2 (Wi-Fi) | A8X | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ricktav, mattonik |
```

Add under the table, or as a J81 footnote:

- GPU ❌: compositor is CPU-only; the A8X GPU core ID is readable with DWI held on.
- Sound ✅: both speakers. Not the 3.5 mm jack, not the microphones.
- Bluetooth ✅: headphones (A2DP) and keyboard/touchpad. Wideband (mSBC) call audio does not flow.
- Charges ✅: 1.5 A from a computer CDP or Apple USB-C adapter. Apple USB-A brick not tried.
- Rotation ❌: no accelerometer/AOP yet.

**Features table (live today, keep):**

```
| j81 | working | working | working | missing | working | working | missing | missing | missing | missing | working | working | working | working | working | none | working | working | working | working | working | working | working | missing | working | missing | missing | missing |
```

**Proposed Features row:** unchanged. Optional comment in `devices/j81/device.toml` (already present for speakers, BT crackle, charging sources). Regenerating the matrix would pick those up only in toml comments, not in the table.

**Drivers table (live):** speakers / charging / BT all `yes`. Accurate. No correction.

**J82 glance (for comparison; not a J81 error):**

```
| iPad Air 2 (Cellular) | A8X | 🤔 | ❌ | 🤔 | 🤔 | 🤔 | 🤔 | 🤔 | 🤔 | ❌ | – |
```

Keep 🤔 until someone runs J82. After a successful port-test, copy J81’s W cells except `cellular` (still M).

---

## Task 3 — next features (J81 first, then porting wins)

Do not implement the large items here. Effort is relative (DT/glue vs new reverse-engineering vs GPU stack).

### Top five for J81

| # | Feature | Effort | Builds on | Risk |
| --- | --- | --- | --- | --- |
| 1 | **Validate J82** (cellular Air 2): speakers, charging, storage, BT 3 Mbit/s | Small (test + toml) | Shared `t7001-air2.dtsi`; Henrik already enabled speakers/charging/SmartIO firmware on J82 | Cellular baseband must stay off (`cellular = missing`). Modem power wells unknown. |
| 2 | **GPU desktop** | Large (userspace + kernel) | `t7001/0012` DWI always-on; core ID `0x00070500` measured; n102 A8 GPU desktop is **W**; OrchardLinux/gpu A8X notes | A8X is three clusters vs A8; wrong power sequence hangs the bus (exactly what 0012 prevents). No dEQP yet. |
| 3 | **Headphone jack + mics (CS42L81)** | Medium–large | `docs/j81-audio.md` (MCA0, SPI1, CS GPIO 157, IRQ 116); SIO V1 and MCA v1 already in tree; J71b jack switching as UX model | Codec is not MAX98721. Wrong SPI/CS can lock the bus. Mic bias / jack detect untested. |
| 4 | **AOP / accelerometer (rotation)** | Medium–large | J71b/J171 `apple_aop_accel` + mount-matrix; J81 has no AOP DT | A8X always-on block may not be the A9/A10 AOP. Wrong firmware brick-risk is low (RAM boot) but bring-up is slow. |
| 5 | **Speaker protection + amp IRQs** | Medium | `max98721.c` IRQ path; DT GPIO 8/9 + 101; iOS `SpCl` / IV-sense | Until IV-sense works, keep the −12 dB clamp. Wiring IRQs alone is a **small** first step (log thermal/OC). |

### Other J81 follow-ups (smaller)

| Feature | Effort | Builds on | Risk |
| --- | --- | --- | --- |
| Wire MAX98721 interrupts in DT (no protection model yet) | Small | `0017` comments, `0023` irq handler | IRQ storm if flags are level and uncleared |
| Test Apple USB-A brick (BrickID) and a cheap DCP | Small (lab) | existing `tristar_identify_usba` | Could grant up to 2.4 A; watch pack temp |
| mSBC / HFP SCO | Medium | BCM4350C2, hci_uart, PipeWire | May be userspace; #195 already ruled out `brcm,bt-pcm-int-params` |
| Light sensor | Small–medium | `tsl2583` + LSCI on A9/A10; Air 2 has ALS in ADT | Need the I2C/HID path from the ADT |
| Lightning accessories | Medium | `APPLE_TRISTAR_ACCESSORY` off on apple-4k | Enable in both configs; test ID bus |

### Quick wins to port *between* boards (not J81-specific)

| Port | From → to | Effort | Notes |
| --- | --- | --- | --- |
| Confirm charging_control on J171 | J71b Tristar in `t8010-ipad6.dtsi` | Test only | J171 charging is W; control is U with “same node as iPad 6” |
| J172 / J72b | J171 / J71b | Test | Identical binds; cellular **M** |
| A7 speakers toml | J72 W-path → mini 2/3 | DT audit | Catalog binds speakers on J85* while toml says missing — either disable the node on minis or mark untested and try |
| A7 HSIC Wi-Fi catalog | J85 W | Catalog | Teach `feature-drivers.toml` `apple-a7-wlan` so Drivers matches Glance |
| N66 Wi-Fi / BT | n102 / t7000 uart+pcie | Medium | toml already names BCM4350/4345 on PCIe1 and uart1/4 “not in s800-0-3.dtsi yet” |
| J96 charging | J81 D2207 / J71b Tristar | Medium | mini 4 charging **M**, no bind; different PMIC likely |
| A9 mic catalog | J71t W | Catalog | `audio_input` should recognise the A9 path, not only t8010 PDM |

---

## Branch changes

Only the DCO lines on the four #197/#195 patches, plus this report. ANS1 CPU-stop and `DEBUG 1` left unfixed (need a storage reboot test; not “obviously correct” without hardware).

Patch-apply: **PASS** for apple-4k / `j81`. Kernel image: not compiled (no aarch64 Podman toolchain on this VM).
