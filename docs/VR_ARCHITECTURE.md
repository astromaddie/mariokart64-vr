# Mario Kart 64 Recompiled VR architecture

## Target and current evidence

The target is a standalone Steam Frame running a native Linux AArch64 build through Steam's
ARM64 runtime. The flat renderer uses Vulkan through SDL2 and RT64. An Android/Lepton route is
not part of the current build path.

The original upstream flat build is the baseline for future renderer work. The source uses the
RT64 revision pinned by `lib/rt64`; it does not contain the Plume VR hooks present in the newer
DK64/Banjo renderer. Keep the original game/runtime and renderer context as the baseline, then
assess a renderer-only migration separately. No RT64 upgrade or VR rendering change is included
in this build-foundation step.

The pinned-source ARM64 build, package and dependency checks pass. A 30-second Xvfb/lavapipe
smoke run loaded the application UI assets and stayed open until its timeout. The package's
`BUILD-METADATA.json` and `build-linux-aarch64/logs` record that host evidence. The smoke image
has no D-Bus session bus, so SDL prints a D-Bus assertion during timeout shutdown. A separate
native probe created a SteamVR/OpenXR session and submitted one stereo frame. The game itself
has not launched on the Frame, and the probe's eye colors have not been visually checked because
the device was unworn. These results do not establish game VR readiness.

## Camera and simulation

The game owns up to four `Camera` records. Each contains a world-space position, look-at point,
up vector, collision state and a player id (`lib/mk64/src/camera.h`). Race cameras follow their
assigned kart; the game also has mode-specific camera paths. This source camera is a chase view,
not a head pose. The game produces N64 display lists, while RT64 interprets their RSP model-view,
projection and viewport state. The current `RT64Context::send_dl` resets RT64's RSP state and
processes each display list; `update_screen` calls the ordinary RT64 presentation path.

The project advertises high-refresh rendering with the original game logic unchanged. The
relationship between the game's VI/tick callbacks, RT64 interpolation, and a future
`xrWaitFrame`-paced loop still needs a production-path audit. Until then, do not advance game
state per eye or replace the renderer's existing presentation cadence by assumption.

## Draw and viewport inventory

This is the initial inventory from the game camera structures and RT64 RSP/RDP path. It names
the work categories; it does not claim every display-list branch or special effect has been
audited.

| Draw path | Current source path | Future stereo rule | State |
| --- | --- | --- | --- |
| Track, kart and other 3D geometry | Game display lists through RT64 RSP matrix stacks and raster draw calls | Render the original world transforms once per eye with eye-offset view matrices; retain depth and texture effects | Not started |
| One-to-four player viewports | Per-camera game viewport/projection state and RT64 viewport/scissor data | Inventory split-screen modes and map each active player camera to its own full-eye projection before implementation | Not started |
| HUD, menus and 2D sprites | Game display lists and RT64 RDP/S2DEX-related sprite paths; exact draw sites remain to be traced | Classify each layer and place it on a stable quad or deliberate in-world surface; preserve alpha and ordering | Not started |
| Sky, fog, screen effects and transitions | RT64 display-list/RDP state and game-specific effect passes; exact per-scene use remains to be traced | Preserve the game's effect timing once per XR frame and verify coverage at synthetic yaw angles | Not started |
| Native culling and clipping | Game display-list branches, RT64 RSP transform/cull state, and RDP scissor rectangles | Test back/near geometry and all camera yaw directions; classify any screen-space culling assumptions | Not started |

## Renderer and input boundaries

Linux creates an SDL Vulkan window. `RT64Context` passes the SDL window to RT64, submits the
game's display lists, and presents with RT64's normal `updateScreen` call. There is no OpenXR
instance, session, Vulkan XR binding, swapchain, per-eye camera, or OpenXR controller action
path in this source state.

The game input callback polls the existing SDL/game-controller mapping path and feeds the
runtime's N64 pad state. The Steam Frame profile and how SteamVR exposes that controller to SDL
must be checked through a Steam launch on the device.

## Frame protocol and probe gate

No XR frame protocol is implemented. A later stereo path must take display time and poses from
`xrWaitFrame`, advance simulation and animation once per XR frame, render a complete pass per
eye first, then submit one projection layer. The graphics binding and swapchain format are
measured by the standalone Vulkan OpenXR colour probe: SteamVR/OpenXR 2.17.10 accepted two
1728×1728 sRGB swapchains with UNORM views on a Turnip Adreno 750 GPU.

The probe submitted one valid stereo frame while the device was in `SYNCHRONIZED`. Visual
confirmation of distinct left/right colors is still pending. The probe does not render game
content and is not evidence of stereo gameplay.

## Status

| Milestone | Status | Evidence |
| --- | --- | --- |
| Linux AArch64 flat build, package and ABI | Passed on host | ARM64 ELF, staged dependency closure and package metadata; `GLIBC_2.34` maximum, no `GLIBCXX` requirement |
| Xvfb/lavapipe launch smoke | Passed for 30 seconds | UI assets loaded; process remained alive until timeout; D-Bus assertion occurs at shutdown in the bus-less container |
| Steam Frame install and flat launch | Not started | Device execution is pending |
| Flat Steam launch and persistent data | Not started | Requires Frame connection and a Steam devkit title |
| Standalone Vulkan OpenXR colour probe | Submitted one stereo frame | SteamVR/OpenXR 2.17.10, Turnip Adreno 750, two 1728×1728 sRGB swapchains with UNORM views; device was in `SYNCHRONIZED` and unworn, so visual eye-color confirmation is pending |
| Stereo gameplay and HUD inventory | Not started | No VR render path |
| User headset play | Not started | The game build has not been worn or visually checked |
