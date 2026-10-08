# Steam Frame performance measurements

These measurements precede the supplied close-up kart and 3D item import. The
new visuals use the saved 2160×2160/120 Hz profile; these earlier timings do not
establish their frame rate.

## Revised standard/full-detail racers

The native application built from `f1ee10c450d91fdeb0d79e19c3691e2d00623bb7`
(SHA256 `d8ffc8aacc5d0b88c7fddf68f39f8b0d92e2d073ede72460564081636efc93ec`)
with external model NRM `26a3afd600aeb5c6b56857443bb197bd85da633439617a3c17856083d12a02c7`
was measured through the same Steam title at 2160×2160 per eye and actual 120 Hz,
with saved LOW camera smoothing and foveation off.

A selector-free 90-second Luigi Raceway run with image readback disabled produced
five settled stereo windows, each at 120.0 presentations/s with zero missed
predicted periods. Both-eye GPU times were 3.69, 3.17, 3.10, 3.29 and 3.47 ms.
The full CPU/display period was 8.33 ms, including `xrWaitFrame`. All 68 common
simulation samples at game frames 630–2640 exactly matched the stock flat baseline
across game state, race clock, all-player digest, player position/speed/lap/rank.

A preceding run with image readback had occasional single misses and 119.8–120.0
presentations/s; those capture windows are not counted as zero-miss results.
These are unattended, stationary-player measurements with AI advancing. Full-race
loads, extended thermals and the revised package's worn comfort remain unmeasured.

The clean native log SHA256 is
`9ed5036416106d89b591462187a12153a929fe6a3375532a42b8e78b4338489b`;
local evidence and `simulation-parity.json` are under ignored
`build-linux-vr-validation/wear-fixes/candidate/f1ee10c…/perf-noreadback/`.

## Earlier model-package measurements

2160×2160 per eye at an actual 120 Hz passed three native 90-second runs with the
Amped Up 3D racers enabled. These runs used camera smoothing off. The selected Frame
profile uses that resolution and rate, with foveation off; the subsequent camera
smoothing activation is described in [VR architecture](VR_ARCHITECTURE.md#camera-and-simulation).
This is unattended Luigi Raceway evidence; wider course, effect, sustained thermal
and wearer acceptance remain pending.

Measured on the native AArch64 Frame build on 2026-10-08, through the Steam title
`Devkit Game: MarioKart64VR` (shortcut app ID `2690512207`). The executable SHA256 is
`dbcd585ee9f890b136181378adadde7dd9e2fc3e690cc025be294bcb17850ca2`, built from
`dd3d7a191b606e8ef0830588a89e8bf8c60df562`. The external Amped Up racer mod SHA256 is
`4ba53056ba7428b99d2aa189e1bf662fdfc8ab1d7b7ad951bfd358d8bd2437a8`.

## 120 Hz results

Every run measured an 8.333 ms `predictedDisplayPeriod` and actual 2160×2160 eye
swapchains. Each contains four settled 10-second stereo windows after the first
transition window:

| Run | Settled presentations/s | Settled missed periods | Both-eye GPU | CPU frame work | Stock simulation samples |
| --- | --- | --- | --- | --- | --- |
| 1, with image readback | 120.0 | 0 | 3.08–3.10 ms | 0.75–0.87 ms | 68/68 match |
| 2, without readback | 120.0 | 0 | 3.09–3.10 ms | 0.79–0.93 ms | 68/68 match |
| 3, without readback | 120.0 | 0 | 3.09–3.10 ms | 0.81–0.88 ms | 68/68 match |

The additional `xrEndFrame` CPU cost was 0.08–0.10 ms. Full CPU period includes
`xrWaitFrame`, so the reported 8.33 ms is not the CPU rendering cost. Simulation
stayed at its original 30 Hz; display cadence is independent. All 68 common samples
at game frames 630–2640 matched the stock baseline in each run. All three processes
exited cleanly through the diagnostic exit path.

The startup/cinema/first stereo windows reported 5, 1 and 1 missed predicted
periods respectively across the three runs. Run 1's first stereo window, which
included the image readback, reported 119.6 presentations/s and two misses.
Runs 2 and 3 had zero misses in all five stereo windows. These counters measure
the app's predicted display cadence, not a separate compositor dropped-frame audit.

These measurements use an unworn headset and a stationary player kart while the
original AI racers advance. Both submitted 2160×2160 eye images and the separate
1080×1080 HUD from run 1 were inspected. Readbacks were disabled in the repeats.

The normal shortcut uses `./LAUNCH-STEAM-FRAME.sh --game mk64`, with only
`APP_FOLDER_PATH` in its saved environment. Diagnostic autostart, forced unworn
rendering, dumps and automatic exit are disabled. During this performance check,
only `refresh_rate = 120` and `resolution_scale = "auto"` changed in the saved game
configuration. The later camera check selects `camera_smoothing = "low"` separately.

Local full logs, launchers, image hashes, comparisons and the final device state
are retained under ignored `build-linux-vr-validation/performance/`, with one
directory for each run and `summary.json`. Native log SHA256 values are:

- Run 1: `05cefebf07dbb795a1cb99118f1bab3f994a7b1450b3e37cfbd3cf17cdc26440`
- Run 2: `fbdb162148c7344aca8fd4df74fc5e76ab3a38ca9117eb93119ba7f41f13679a`
- Run 3: `7115a1ad928cbd1b92f38d5b441c99cc8901f72d7ad62a52fe1fe38e78a06c00`

## Camera smoothing enabled

An additional native 90-second run used the saved `camera_smoothing = "low"` on
the same binary and Amped Up mod. All four settled 10-second stereo windows
reported 120.0 presentations/s, zero missed predicted periods and 3.09–3.10 ms
GPU time for both eyes. The first stereo transition/readback window reported
119.7 presentations/s and two misses. All 68 common simulation samples matched
the stock baseline; the process exited cleanly. Submitted eye and HUD images were
inspected. This stationary-player run does not measure driving-camera motion or
wearer comfort.

Local evidence is retained under ignored
`build-linux-vr-validation/camera-smoothing-low/`; the native log SHA256 is
`96ebb51919cca30cd4485f254d45bca695c7942e732eac035afb944e56ae0dea`.
`normal-launch-verification.json` records the actual normal Steam process resolving
the VR data folder after the launcher fallback correction, without diagnostic
environment overrides. The saved configuration retains 120 Hz, automatic resolution
and smoothing `low`, with diagnostic flags disabled.

## Live per-title refresh selection

The installed SteamVR `vrcmd` can change the same per-title setting through the
running runtime. Its read form takes a single dotted setting path; its setter
takes that path and the numeric value as separate operands:

```sh
/opt/steamvr/bin/linuxarm64/vrcmd --set-settings-int steam.app.2690512207.preferredRefreshRate 120
/opt/steamvr/bin/linuxarm64/vrcmd --settings-int steam.app.2690512207.preferredRefreshRate
```

The readback returned `120`, and SteamVR persisted that app's `preferredRefreshRate`
as `120`. Relaunching the game through Steam then produced an actual 8.333 ms
`predictedDisplayPeriod`, with 120 Hz offered and current. No SteamVR or Steam
client restart was required. Other titles' settings were unchanged.

Use `resolution_scale = "auto"` in the app's `vr.toml` or
`MK64_VR_RESOLUTION_SCALE=auto` for the 2160 target. A numeric scale multiplies the
runtime recommendation, so `1.25` would overshoot if that recommendation were
already 2160. The measured recommendation here remained 1728; `auto` produced
2160×2160 eye swapchains. Set `refresh_rate = 120` in the same app configuration.
The Steam per-title choice determines the available rate; the app request alone
was insufficient.

This app ID belongs to this installed devkit shortcut. Read the intended title's
actual shortcut app ID before applying the command to another installation.
Book the shared Frame and preserve its app settings before changing them.

## Why the app request alone was insufficient

The first 90-second run requested 120 Hz and used a numeric resolution scale of
1.25. Its submitted images were 2160×2160, but SteamVR offered only 72 Hz for the
title and its actual display period remained 13.889 ms. It passed 68 simulation
samples and clean exit; the four settled windows reported 72.0 presentations/s,
zero missed periods and 3.10–3.12 ms GPU time for both eyes. This establishes
resolution performance at 72 Hz, not 120 Hz. The per-title runtime setting above
was necessary to obtain the separately measured 120 Hz runs.

That earlier evidence remains in `performance/2160-120-attempt1/`. The initial
Frame game settings, Steam sidecars, SteamVR settings, log and captures were
preserved in `~/devkit-game/MarioKart64VR/perf-backup-20261008-2160-120` before testing.
