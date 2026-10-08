# Mario Kart 64 Recompiled VR architecture

## Target and current evidence

The target is a standalone Steam Frame running a native Linux AArch64 build through Steam's
ARM64 runtime. The flat renderer uses Vulkan through SDL2 and RT64. An Android/Lepton route is
not part of the current build path.

The original renderer package remains the flat comparison baseline in
`build-linux-aarch64/package/MarioKart64Recompiled`. Source now adopts the author's
`upstream/NewFrontend` revision `621e7323692c98a1c1c944a0a19db88e94e51246`, with modern
RT64/Plume, RecompFrontend and N64ModernRuntime. This is an explicit author-base upgrade,
not a renderer-only backport. It retains the ARM64 build/provenance scripts and probe.
The author's changes also alter audio/input, object angular culling and jumbotron guards;
they must be distinguished from subsequent VR changes. The stock author frontend is retained;
no custom VR UI or assets are approved or implemented.

The pinned-source ARM64 build, package and dependency checks pass. A 30-second Xvfb/lavapipe
smoke run loaded the application UI assets and stayed open until its timeout. The package's
`BUILD-METADATA.json` and `build-linux-aarch64/logs` record that host evidence. The smoke image
has no D-Bus session bus, so SDL prints a D-Bus assertion during timeout shutdown. A separate
native probe created a SteamVR/OpenXR session and submitted one stereo frame. A second probe
run read back those submitted images and verified distinct uniform left/right colors on the
Frame GPU. The flat game launches through Steam and its launcher has been captured through
Gamescope. The original flat game reached attract-mode racing on the Frame. The modern diagnostic flat
package `15343d9c…584a7` reached a real one-player Luigi Raceway race through the original menus:
production frames 630–1140 advanced 30/second while VI advanced 60/second, and the race timer,
AI state digest and audio counters advanced. The corrected native VR package `d770b106…a5a0743b`
matched all 68 common simulation samples at game frames 630–2640, including native race clock
and all eight players. Actual submitted eye/HUD images were inspected at yaw 0/90/180/270.
The final clean-source package `dbcd585e…7850ca2` also passed a native 60-second stock run
with the saved 0.05 m near plane: its 38 common simulation samples at frames 630–1740
matched the same flat baseline, and its submitted eye image retained the corrected floor.
The user authorized proceeding with controllers assumed to work; controller and wearer
playtesting remain unverified. Only Luigi Raceway has unattended game-scene coverage.

## Camera and simulation

The game owns up to four `Camera` records. Each contains a world-space position, look-at point,
up vector, collision state and a player id (`lib/mk64/src/camera.h`). Race cameras follow their
assigned kart; the game also has mode-specific camera paths. This source camera is a chase view,
not a head pose. The game produces N64 display lists, while RT64 interprets their RSP model-view,
projection and viewport state. The current `RT64Context::send_dl` resets RT64's RSP state and
processes each display list; `update_screen` calls the ordinary RT64 presentation path.

`patches/frame_report.c` publishes one native camera/scene snapshot at the end of each game
frame. The host retains RT64 workloads and renders both eyes from one predicted head pose;
it does not rerun game logic for each eye. The existing game VI and 30 Hz simulation stay intact.
Standby pauses at the publication boundary outside game locks, unless the explicit unattended
`force_render` diagnostic is enabled. Menus, pause and split screen use cinema/panel modes.
The original letterboxed race intro stays in cinema until the native race clock advances;
both the scene classifier and render-only patches use that same boundary.

The installed Frame profile enables `camera_smoothing = "low"`. The existing
`CameraSmoother` uses the Star Fox-style uniform quadratic B-spline over three
source frames, evaluated at each display frame's interpolation weight. This smooths
the game camera's position and orientation with about half a game frame of additional
delay (16.7 ms at Mario Kart's 30 Hz). One rigid correction is shared by both eyes and
the world/sky camera groups. The predicted OpenXR head pose is applied separately;
physical head movement is not filtered. Scene changes and large camera jumps reset
the history, and cinema/first-person views bypass the filter.

The renderer already contained this code in package `dbcd585e…7850ca2`; the first
baseline and the three initial 2160/120 measurements deliberately used `off`, which
retains RT64's linear interpolation. Enabling `low` requires only the saved setting,
without recompiling the application. `medium` and `high` add orientation followers
of 0.06 s and 0.12 s; those extra filters are not selected. Star Fox's base cockpit
smoother has no such follower and runs at 20 Hz, adding about 25 ms instead.

A native 90-second run with saved `low` passed at 2160×2160 per eye and 120 Hz:
four settled 10-second stereo windows had zero missed predicted display periods,
and all 68 common simulation samples matched the stock flat baseline. Submitted
eye/HUD images were inspected. The player was stationary while AI racers advanced;
this verifies activation and rendering, with driving feel and wearer comfort pending.
Full local evidence is in ignored `build-linux-vr-validation/camera-smoothing-low/`.

The normal Steam launcher also resolves its data folder from the package's
`APP-DATA-NAME` file when Steam omits the devkit environment sidecar. VR packages
specify `MK64FrameVR`; explicit `APP_FOLDER_PATH` overrides retain precedence.
The actual normal native process was verified using this folder with saved `low`
and no diagnostic environment overrides. This launcher correction leaves the
application binary unchanged.

## Draw and viewport inventory

This inventory traces the shared production paths. It is not exhaustive certification of
all course display lists or object variants.

| Draw path | Production entry point | Required VR treatment and current limit |
| --- | --- | --- |
| 1P world projection | `patches/camera.c:render_player_one_1p_screen`, group `0xFFFFAAAA` | Original chase view plus one predicted head pose; retained workload replay per eye. Split groups `0xFFFFAAAB..AAB2` stay on cinema. |
| Course visibility | `render_course_segments` | Preserve track-section/collision selection. Each section selects one of four directional lists using the latest predicted head yaw only on the VR draw path. Sector-edge coverage still needs device inspection. A naive union is unsafe: lists carry state, nested calls and transparent surfaces. |
| World object culling | `patches/render_distance.c:is_within_render_distance` | Preserve radial limits while removing camera angular rejection only on the VR rendering path. |
| Object visibility flags | `is_object_visible_on_camera` | Used by update/visibility accounting as well as rendering; requires care before widening. |
| Kart camera collision | `check_player_camera_collision` | Also called by AI/player simulation. Must remain unchanged; it is not a rendering-only gate. |
| Stock kart/player | `object_tagging.c:render_player`, `improvements.c:render_kart` | Preserve player transform tags and palette/TLUT behavior. Optional private 3D-racer NRM replaces only the kart draw. |
| HUD | 1P camera tail calls `func_80058BF4`, `func_80058C20`, `func_80093A5C`, `render_hud`; `patches/hud.c` | Distinguish HUD projection group from world before the first HUD draw; retained black/white solve for a transparent quad. |
| Gradient sky/ground | `background.c:func_802A4A0C`, native `func_802A487C` | VR 1P uses a 16-sector surrounding gradient with original course colours, tagged 0xFFFFAAE0 and rendered without eye/head translation. Flat retains original quads. |
| Clouds/stars | `func_800788F8` updates visibility/screen X; `object_tagging.c:func_80051ABC` draws textures | Authored yaw and height live in the object. VR 1P builds tangent quads from authored yaw/height, retaining textures and star alpha. Segmented vertex addresses are translated before CPU reads. Alignment remains a device check. |
| World billboards | `object_tagging.c`, including bats and paletted objects | Identify camera-facing groups separately from kart models; preserve textures and face the centre-eye view. |
| Scissors/aspect | background fixed scissors; HUD extended scissors; world viewport | Eye projection uses runtime asymmetry; HUD keeps original alignment on its own panel. |
| Jumbotron | `patches/jumbotron.c` Luigi Raceway/Wario Stadium previous-frame crops | Preserve offscreen framebuffer draws/copy timing once per game frame, never copy one eye into simulation. |
| Transparency/fog | Course/object display-list state | Preserve native order and fog coefficients when eye near plane changes; do not merge directional lists without state/order proof. |

## Game-frame diagnostics

`--game mk64` (also `mk64.us`) starts only after the stored US ROM passes the runtime's
existing hash validation. The launcher remains available when no valid ROM is stored.
`MK64_DIAG_FRAMES=N` records every Nth production `end_master_display_list` call:
VI/audio/rumble callback counters, game state, screen mode, course/demo/pause, native game
timer/race clock and a digest of all eight racers' positions, speed, lap and rank. Camera
and wall time are excluded from the state digest. The MIPS/native structure is statically
checked. This instrumentation does not by itself prove flat/VR parity.

`MK64_DIAG_AUTOSTART=45` enables a bounded deterministic native-pad script: Start at game
frame 150, then A every 45 frames, held for five frames. It stops on entry into a real 1P
race or at 45*30 game frames. It changes no menu/race variables directly and is off by
default. Controller playtesting remains pending.

## Renderer and input boundaries

`MK64_VR` defaults OFF. ON installs the committed generic host from Banjo revision
`b426f05f3722a4e947a5c224601e906eff158c65`, with Mario Kart scene/profile/input adaptations.
RT64 is pinned to `0b59675ded29a010f5035600d88e877046f7c9d3` and Plume to
`1699a49cabc1a29d9470d9ee5192b7c176865c17`. The author frontend stays at
`c3bc7a2e9eff532c7f55b28d78fc4e07afb923aa` with runtime
`6021a7d9f6e970ebdd078951441502343f3b0453`; the older Banjo frontend API is incompatible.
No modifications to those dependencies are required. If no OpenXR runtime is present, the application falls back to the stock flat UI.

OpenXR uses the Steam Frame controller profile first and merges real actions into the N64 pad.
A is accelerate/confirm, X is brake/B, left bumper/trigger Z, right bumper/trigger R,
left stick-click L, right stick-click C-up, and B/Y/right stick retain C-buttons. Steering stays
kart-relative regardless of head yaw. View retains recentre and the original frontend access.
Manual Steam dashboard reopening is not disabled. Controller operation is assumed at the user's
request, not playtested. Custom VR menu entrypoints are deliberately inactive; configuration is
`vr.toml` under the app data folder or `MK64_VR_*` environment overrides.

The initial calibration is explicitly provisional: 10 game units/metre, with the stock chase
camera, source pitch, runtime eye separation and a 0.05 m VR near plane. The source 9-unit
near plane becomes 0.9 m at this scale and visibly clips the floor at headset FOV; actual
Frame eye captures confirmed that 0.05 m removes the strip. RT64 remaps fog from the source
projection when changing the near plane. It is not a measured kart
height. The source profile requests the runtime recommendation and 72 Hz; foveation is off.
The installed Frame title's higher-resolution 120 Hz measurements and per-title configuration
are recorded in [Frame performance](FRAME_PERFORMANCE.md).
World scale can be adjusted with `MK64_VR_WORLD_SCALE`. No physical dimensions are inferred
from the Amped racer colour tables or collision radius.

## Frame protocol and probe gate

The host uses `xrWaitFrame` prediction, one pose for both eyes, RT64 eye slots, Vulkan
swapchain images, and a distinct transparent HUD quad. The HUD is tagged 0xFFFFAAE1 and solved
from black/white retained passes. The standalone colour probe measured SteamVR/OpenXR 2.17.10
accepting two 1728×1728 sRGB swapchains with UNORM views on a Turnip Adreno 750 GPU.

The readback probe submitted one valid stereo frame and verified every pixel of the left
image as RGBA `230,13,26,255` and the right image as `13,38,230,255`. It copied the same
acquired images that were released and submitted, after rendering through UNORM views. The
device was unworn. The probe does not render game content and is not evidence of stereo gameplay.

## Status

| Milestone | Status | Evidence |
| --- | --- | --- |
| Linux AArch64 flat build, package and ABI | Passed on host | ARM64 ELF, staged dependency closure and package metadata; original `GLIBC_2.34`, modern author-base `GLIBC_2.35` maximum, no `GLIBCXX` requirement |
| Xvfb/lavapipe launch smoke | Passed for 30 seconds | UI assets loaded; process remained alive until timeout; D-Bus assertion occurs at shutdown in the bus-less container |
| Steam Frame install and flat launch | Attract racing verified unattended | Native original package `d6d40e9c…26d`; Gamescope capture shows Yoshi Valley split-screen attract race |
| Modern flat race and rates | Verified unattended | Real 1P Luigi Raceway via scripted original menus;30 game frames and 60 VI per second; data outside the package |
| Standalone Vulkan OpenXR colour probe | GPU readback and submission passed | SteamVR/OpenXR 2.17.10, Turnip Adreno 750, two 1728×1728 sRGB swapchains with UNORM views; distinct uniform colors verified across the submitted images |
| Native VR build, package and ABI | Passed | Final clean-source package `dbcd585e…7850ca2`; GLIBC 2.35 maximum; actual native 1P eye/HUD submission |
| Bridge/profile/retained-eye tests | Passed | Four host suites plus seven sfvr suites; production scene classifier, controller mapping and head-independent steering |
| Stereo gameplay and simulation parity | Verified unattended | Cardinal-view candidate matched all 68 common simulation samples at frames 630–2640; final package matched all 38 samples at 630–1740 and exited cleanly at 60s |
| Viewport, HUD and full-course coverage | Luigi Raceway cardinal views and HUD inspected; broader coverage pending | Actual yaw 0/90/180/270 eye images and settled HUD; intro cinema transition confirmed; 0.05 m near-plane floor correction inspected separately |
| Private Amped Up 3D racers | Built, installed and native rendering verified unattended | Final external NRM `4ba53056…2437a8`; 269 model lists validated, ten importer tests passed, submitted eyes/HUD inspected and 38 final simulation samples matched stock |
| 2160×2160 per eye at 120 Hz | Verified unattended on Luigi Raceway | Three 90-second runs with the final model mod; actual 8.333 ms period, twelve settled windows at 120.0 presentations/s with zero missed periods, approximately 3.1 ms both-eye GPU; 68 simulation samples matched stock per run. See [performance details](FRAME_PERFORMANCE.md). |
| User headset play | Not started | Unworn submitted GPU images inspected; controllers assumed by user request; wearer playtesting remains pending |

## Reproduction

Build with the same pinned native ARM64 image and verified ROM input:

```sh
MK64_ROM=/tmp/mariokart64-vr-build-rom.z64 MK64_VR=ON BUILD_DIR=build-linux-vr JOBS=8 tools/docker/build-linux.sh all
cmake -S src/vr/tests -B build-vrtest
cmake --build build-vrtest -j8
ctest --test-dir build-vrtest --output-on-failure
cmake -S third_party/sfvr -B build-sfvrtest
cmake --build build-sfvrtest -j8
ctest --test-dir build-sfvrtest --output-on-failure
```

For unattended diagnostic eye captures only, use a fresh app data folder containing the
validated `mk64.us.z64`, set `APP_FOLDER_PATH` in the launcher environment, and launch:

```sh
MK64_DIAG_AUTOSTART=90 MK64_DIAG_FRAMES=30 MK64_VR_FORCE_RENDER=1 \
MK64_VR_DUMP_FRAME=120 MK64_VR_DUMP_IN_PLAY=1 MK64_VR_DUMP_COUNT=4 \
MK64_VR_DUMP_INTERVAL=720 MK64_VR_DIAG_YAW_STEP=90 \
MK64_VR_DIAG_EXIT_SECONDS=90 MK64_VR_TIMING=1 ./LAUNCH-STEAM-FRAME.sh --game mk64
```

`vr-dumps` in that data folder receives actual submitted eye/panel/HUD images with yaw 0/90/180
/270 suffixes. Forced rendering while unworn is not wearer acceptance. Check world and HUD alignment,
course-sector boundaries, stock billboard/visibility omissions, cloud placement, transparency,
and jumbotron contents. Native AI/camera-collision and object-update visibility are intentionally
unchanged; full 360-degree object coverage is not yet established. The model NRM has its own
runtime gate and should remain disabled for the stock-renderer comparison.

The final stock VR package is `build-linux-vr-release/package/MarioKart64Recompiled`
(binary SHA256 `dbcd585ee9f890b136181378adadde7dd9e2fc3e690cc025be294bcb17850ca2`),
built from clean source revision `dd3d7a191b606e8ef0830588a89e8bf8c60df562`.
The matching OFF package is `build-linux-flat-release/package/MarioKart64Recompiled`
(binary SHA256 `1f8e61198756bc25f0ffacaa9486e4b80e40a66d3d06d005a64f9dfd8c2e570f`).
Each retains its matching unstripped executable above `package/`. The earlier cardinal-view
snapshot `d770b106…a5a0743b` is preserved in `build-linux-vr-intro2/`. Its separate near-plane
run used `MK64_VR_EYE_NEAR_M=0.05`; the final source makes that value the VR default.
Local evidence, logs and the comparison JSON are preserved under ignored
`build-linux-vr-validation/stock/`; the comparison excludes presentation/camera fields.

The Frame's Steam shortcut `Devkit Game: MarioKart64VR` uses the ordinary package launcher
with `--game mk64` and app data at `~/.local/share/MK64FrameVR`. Diagnostic autostart,
forced unworn rendering, image dumps and automatic exit are disabled in the normal shortcut.

## Render invariants and limitations

Active immersive 1P uses the full 320×240 source viewport/scissor before world and sky.
The original race intro remains in cinema; neither screen dimensions nor simulation camera
wrappers are changed. The cloud draw restores its perspective after the native HUD wrapper.
The surrounding gradient keeps original course colours and cloud/star textures.

The optional OpenXR hidden-area mask is off by default; `RT64_VR_HIDDEN_MASK=1` enables it
for diagnostics. No RT64 changes were needed beyond using the pinned retained-eye fork.

The native HUD starts lapX at −40 and timerX at 300, then animates them to 83/228 with
intentional afterimages. That original animation remains. Diagnostic yaw is latched until
the corresponding HUD readback is recorded. Source contracts check sky/world/HUD boundaries,
full immersive viewport restoration, cloud projection and deferred HUD pose handling;
they do not replace GPU image inspection.

Course-sector edges, objects outside the stock visibility envelope, transparency, every
course's sky, jumbotron content, and wearer comfort still need broader playtesting.
Amped courses as additional cups are deferred from this first 3D-racer build;
original courses and cup flow are preserved.

## Private Amped Up 3D racers

[The private importer](AMPED_UP.md) converts the official v3.21 patch's racer renderer
and model data into an external `amped_up_3d_racers` recomp mod. It replaces only
`render_kart`, retaining the original player tags, course rendering and cup flow.
The ROM, patch and generated model NRM are local inputs/outputs and are excluded
from source control. The NRM is installed in the Frame's app-data `mods` directory,
outside the application package; the package's compiled source remains `dd3d7a1`.

The native flat candidate `d69157bc…72e434` showed bounded 3D racers on Luigi Raceway
in a Gamescope capture at game frame 810. All 125 common race-state samples at
frames 630–4350 matched the stock flat baseline. The same mod completed a native
90-second VR run: both submitted eyes and the HUD were inspected at yaw
0/90/180/270, and all 68 race-state samples at frames 630–2640 matched the baseline.
The runtime reported 72 Hz presentation and 30 Hz simulation, with approximately
2.4 ms GPU time for both eyes in the sampled steady scene. These checks used forced
rendering while unworn; they do not establish wearer comfort or controller operation.

The final model NRM SHA256 is
`4ba53056ba7428b99d2aa189e1bf662fdfc8ab1d7b7ad951bfd358d8bd2437a8`.
After the final literal-root coverage repair, this artifact completed a separate
60-second native VR run. Both submitted eyes and the HUD were inspected again,
and all 38 common simulation samples at frames 630–1740 matched stock.
Its importer validates 269 display lists, 3,681 command addresses and 340 vertex
commands; all ten importer/ABI tests and both pinned mod compilation tools passed.

The importer also covers renderer-selected LOD tables and literal model/effect
display lists. The earlier malformed geometry came from an unconverted ROM vertex
operand in a list selected by the renderer outside the initial package-root graph.
The import now rejects unresolved references along those paths and caps the extracted
helper at the original game's 660 effect matrices. Broader special-effect states,
every character animation and every course still need playtesting.

Local submitted images, native logs, import reports and simulation comparisons are
preserved under ignored `build-linux-vr-validation/amped/`. The normal Steam title
`Devkit Game: MarioKart64VR` enables the model mod and runs without diagnostic autostart,
forced rendering, capture or automatic-exit settings.

## Wear-report sprite, HUD and scene checks

The MK64 profile now enables cylindrical facing for its actual world-sprite tags.
RT64 uses the smoothed head-centre world viewpoint shared by the submitted eyes,
with world-up and each sprite's authored scale, mirror and local roll. Tagged
production draws cover actor trees/cows/plants/shells, course props and creatures,
kart particles, flat balloon/chain-chomp alternatives, and bomb bodies/wheels/fuses.
Nested shadow draws use ordinary tags. Real 3D palms, animated creature alternatives
and other solid objects retain their authored matrices. Scratch-position callers
use stable object/bomb identities plus local slots; they do not share the scratch
buffer's address as an interpolation identity.

In immersive gameplay only, normal timer and lap-time cells use the existing
full-opacity one-cycle timer draw. Its exclusive 8×16 rectangles cover the full
rightmost texel; copy mode's fractional inclusive edge clipped that texel at high
resolution. Rainbow/flashing and afterimage timers already use this complete-cell
path. The 104×16 atlas, eight-pixel advance, alignment and native HUD motion remain.
Flat/cinema normal timers retain the retail copy-mode draw.

For bounded native QA, `MK64_DIAG_AUTOSTART=90` enables the original menu/input
script plus optional process-only selectors: `MK64_DIAG_CHARACTER=0..7`,
`MK64_DIAG_COURSE=<retail course id>`, and `MK64_DIAG_STAR_AT=<race second 0..60>`.
Selection is applied before native race initialization. Only the 16 retail Grand
Prix courses are accepted (Moo Moo Farm is 9); unsupported battle courses are
logged and rejected. Star is used once through `apply_star_sound_effect`, after
race start. No option is read without enabled autostart, no selection is persisted,
and diagnostics stop after at most 120 seconds of game frames.
An arbitrary Grand Prix course uses the original debug-course entry flag only
during initialization, then restores the previous flag at the first race frame
(or cancellation/expiry). Otherwise entering a later cup index from a fresh menu
would reuse uninitialized previous-race AI and grid arrays. The regression executes
the production diagnostic and retail setup/spawn selection for all eight characters
on all 16 supported courses, checking a complete unique roster and grid.

For native front/side material and translated-billboard captures, the process-only
`MK64_DIAG_HEAD_X`, `MK64_DIAG_HEAD_Y`, and `MK64_DIAG_HEAD_Z` add metres in the
game camera's axes: X right, Y up, Z backward. For example, with
`MK64_DIAG_AUTOSTART=90 MK64_VR_FORCE_RENDER=1`, `MK64_DIAG_HEAD_X=3` moves the
viewpoint to the right and `MK64_DIAG_HEAD_Z=-10` moves it forward. Pair the
translation with the existing diagnostic yaw to look back toward the racer.
The entire offset is rejected if autostart is not an integer in 1..120, or any
supplied axis is malformed, nonfinite, or outside -20..20 metres. Missing axes
default to zero. Application also requires `force_render` and a synthetic standby
head; wearing the headset leaves the tracked head unchanged. It stops after the
autostart game-frame limit. The offset is added to the shared head after yaw and
before measured eye offsets, preserving tracked motion, IPD and the common
head-centre billboard viewpoint. It is never saved or exposed in the settings UI.

During that bounded run, `[mk64-diag] racer` samples the actual nested display lists
emitted by each visible racer once per second: player/character, commands,
triangles, matrices, list count, effect bits and live RGB. A depth/command limit
reports `truncated=1`, so an incomplete traversal cannot look like a valid primitive
count. The top-level span must lie in the active `gfxPoolExtended` allocation
(`patches/gfx_config.c`); it is above retail 8 MiB RDRAM. Nested lists accept only
aligned addresses within N64ModernRuntime's mapped 512 MiB KSEG0 range, with
checked 16-entry segment lookup and non-wrapping physical base/offset addition.
The log includes `begin`, `end`, `stopped_at`, and `failure`: 0 is complete,
1 invalid address, 2 recursion limit, 3 command budget, 4 invalid top-level span.
The host regression executes the actual walker with only its raw RDRAM read
adapted to host memory, covering expanded-pool counts and each bounded failure.
Compare Wario/Mario and all eight characters with the previous NRM under
the same scene/camera, and inspect both-eye images. Capture several star phases,
Moo Moo Farm side/pass views (with head roll), live timer and completed-lap cells.
Keep one run with all new scene options unset for simulation parity. Host/source
tests and these diagnostic counts do not replace native images or a worn check.
