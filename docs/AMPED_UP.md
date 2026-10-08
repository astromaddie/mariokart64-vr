# Private Amped Up 3D racer and item import

This local importer builds the Amped Up v3.21 3D racer renderer as a recomp mod while keeping Mario Kart 64's original courses and cup flow. It does not import Amped courses or change course selection. The original ROM, official BPS patch, patched ROM, extracted segment, ELF, and generated NRM are private build inputs or outputs; none belong in source control or a distributed release.

## Build the local mod

Provide a verified North American retail `.z64` ROM and the official `Amped_Up_v3.21.bps` extracted from its archive. The project's [official Amped Up page](https://gamebanana.com/mods/613207) identifies the patch source; the importer additionally checks the pinned v3.21 patch SHA-256 and internal CRCs. Populate the repository's pinned `lib/N64ModernRuntime` and `MarioKart64RecompSyms` submodules, then run:

```sh
python3 tools/amped_up/build_mod.py \
  --rom /absolute/path/to/retail-mk64.z64 \
  --patch /absolute/path/to/Amped_Up_v3.21.bps \
  --sdk-root lib/N64ModernRuntime \
  --symbols-file MarioKart64RecompSyms/mk64.us.syms.toml \
  --output-nrm build/amped_up/mod/amped_up.nrm
```

To include the user-supplied close-up kart, add `--kart-source /absolute/path/to/extracted-kart-directory`. The directory must contain all eight `pipeframe64_<character>.dae` variants and their PNG textures. `import_kart.py` uses the standard meshes (6,370 triangles) and preserves their positions/normals/UVs. It separates the 356-triangle steering wheel into a dynamic display list, which rotates with the existing grip steering. The shared 6,014-triangle kart uses each character's authored frame and rim materials. The tyre map is area-filtered from 512² to RGBA16 32×64 for N64's 4 KiB texture memory; other maps retain their 32² source dimensions. Kart scale derives from the source steering ring radius, aligning its centre to the unchanged 18 cm wheel at 28 cm down/forward. The private build report records source hashes, bounds, palette maps, fit, and memory extent.

**Kart credit:** Model made by [fznmeatpopsicle](https://twitter.com/fznmeatpopsicle). The supplied `credits.txt` requires this name/link credit. It does not grant an explicit redistribution license. Keep the supplied art and generated assets private; no model or texture bytes belong in Git or the public application bundle.

New imports also hydrate Amped's green/red shell (51 base + 22 top triangles) and banana (53 triangles) visual graphs. The VR native hooks use their original authored visual scales and shell colors, while retail actors retain collision, ownership, timers, and release physics. Blue shells remain on the existing path. Held 3D props follow trusted controller position and orientation; invalid tracking retains their last local pose on the moving seat, and release resumes native transforms.

A version-2 descriptor at `0x80750000` enables the new visual paths only when the matching private mod is loaded. The supplied kart and wheel replace geometry only for the local first-person draw; chase and other racers retain the existing kart. Removed shared lists still execute their material state, preserving original arms. Omitting `--kart-source` keeps the prior cockpit/wheel and still imports the item visuals. Missing/older mods retain the original visual paths.

Native testing found that the runtime's asynchronous startup framebuffers clear `0x80700000..0x8074AFFF`. The earlier descriptor at `0x8072E3B0` could therefore be erased between initialization and rendering. The new trailer starts beyond both buffers. The importer rejects required display-list, vertex or texture ranges that overlap them; the verified Amped graph ends below `0x80600000`.

The importer checks the source ROM SHA-256 and CRC, official BPS SHA-256 and internal CRCs, and patched target SHA-256 and CRC before creating outputs. It validates the custom segment's location against the original retail heap and static-memory bounds, normalizes skeleton, animation, nested animation-data, and armature-model pointers, and preserves the eight raw three-halfword records at `0x805ADAC8` using the renderer's six-byte stride. The values' meaning has not been established; they are not physical dimensions or scale measurements.

The importer also verifies the eight normal/default rows (index 2, marker 0) at `0x805A5D88 + character * 0x80 + 0x20`, copies each bounded ROM package into its zero-filled fixed RAM root, and applies the stock loader's `G_DL` (`0x06`) and `G_SETTIMG` (`0xFD`) relocation rule. It traverses each package's nine display-list selectors at a 16-byte `G_DL`/`ENDDL` stride and geometry root, model lists reached through both secondary armatures, and all 32 roots selected from the renderer's four checked static LOD/alternate-start tables at `0x805A46C0..0x805A473C`. The extracted renderer also emits seven literal geometry roots at `0x805AADC0`, `0x805AADF0`, `0x805ABB88`, `0x805ABB30`, `0x805ABB60`, `0x805A89B8`, and `0x805A8160`, plus the state-only root `0x805ADA30`. Its indexed state roots are checked at `0x805AD880 + i * 0x30` for all eight racer slots. All reachable lists from these sources are traversed; their `G_DL`, `G_VTX`, and `G_SETTIMG` pointers are converted to segment-0 tokens. This includes the normal Mario alternate-list command at `0x805C7888`, whose source vertex pointer `0x01497228` is relocated to `0x005C78F8`, and the animated limb selected at package offset `0x50`. `G_BRANCH_Z` targets are followed when a preceding `G_RDPHALF_1` supplies one. The importer requires terminated lists, in-range image references, and vertex ranges inside initialized copied bytes. ROM references may cross between imported packages when their destinations are known; unresolved addresses and malformed or unterminated lists fail the import. The current target validates 328 reachable display lists and 4,788 unique command addresses, including 471 vertex commands and 18 texture-image commands; no `G_BRANCH_Z` appears in this closure. The raw extracted segment and hydrated compiler input are written separately, with separate SHA-256 values in `import-report.json`.

The segment-0 convention follows the pinned MK64 source. `lib/mk64/src/main.c` calls `set_segment_base_addr(0, (void*) SEG_START)`; `SEG_START` is `0x80000000` in `lib/mk64/include/segments.h`, and `set_segment_base_addr` masks addresses with `0x1FFFFFFF` in `lib/mk64/src/racing/memory.c`, so segment 0's physical base is zero. That same `memory.c` implementation of `segmented_to_virtual` indexes `gSegmentTable` with the full high byte. Passing original `0x80xxxxxx` KSEG pointers to stock animation code would therefore index outside the 16-entry table. The imported typed CPU pointers use 24-bit segment-0 offsets, and the bounded animation adapter preserves that encoding. Pinned RT64's `RSP::fromSegmented` uses the four-bit segment number and low 24-bit offset, so the GBI tokens address those same bytes through segment 0.

The importer also lowers Amped helper `0x804ADE40`'s original 960-effect cutoff to 660. That helper indexes `gGfxPool->mtxEffect`, whose pinned `GfxPool` allocation has 660 matrices; allowing index 660 or higher would write beyond that array into later pool fields. This bound does not affect the model's vertex/display-list graph.

The build extracts the ten renderer and helper functions from the verified patched image, relocates their direct MIPS calls against the pinned MK64 function symbols, and invokes the pinned `RecompModTool` and `OfflineModRecomp`. The generated source has 14 unique function definitions: ten extracted functions, the `render_kart` wrapper, animation tail-call and CPU-load adapters, and the segment-copy callback. The `render_kart` O32 adapter provides the renderer's fifth stack argument and saves `$ra` beyond its 16-byte argument home area; the stock animation adapter does the same and masks its two pointer arguments to segment-0 offsets. A base (`*`) `recomp_on_init` callback copies the hydrated model data segment to its original fixed address `0x80400000` before game rendering. The NRM identifies `mk64` as its target game without requiring a separate mod dependency. The stock functions called by this closure were byte-compared between retail and Amped ROMs and were unchanged. `OfflineModRecomp` output, the linked ELF/map/disassembly, raw and hydrated segments, import report, and build report are kept under ignored `build/amped_up/`.

The command above keeps the successful package under ignored `build/amped_up/mod/`. Without `--output-nrm`, the desktop default remains `mods/amped_up.nrm`, which the project loads when present. Its fixed Amped model-data range is `0x80400000..0x8072E3AF`; the visual descriptor, optional cockpit and dynamic wheel extend it (the supplied standard kart currently ends at `0x807AF5BF`, checked below `0x80800000`), within expansion RAM and above the retail allocator/static image. The intervening startup-buffer gap carries no required assets. That is a shared fixed-address reservation: other mods must not use this range at the same time. The importer cannot detect conflicts with other installed mods.

For the standalone Frame installation, put the generated NRM in `$APP_FOLDER_PATH/mods/amped_up.nrm` and enable `amped_up_3d_racers` in the frontend's mod selection. The current installation uses `~/.local/share/MK64FrameVR/mods`. Keep the private output outside the checkout's `mods` directory when building the reusable application package: CMake embeds root-level `mods/*.nrm` files. The installed Frame model mod is external to the application package.

The build uses Python 3.11+, Docker with the repository's `mariokart64recomp-frame` image (the script builds it if absent), and the pinned N64Recomp source. The native ModTool binaries are built locally under the ignored build directory when not supplied with `--mod-tool` and `--offline-mod-recomp`.

## Runtime boundaries

The mod force-patches only `render_kart`; player-level renderer tags, shadows, stock course rendering, course selection, and cup behavior stay on the project/retail path. The replacement draws Amped Up's custom 3D racers using the original character selection state and the renderer's existing display-list path.

The project's current `render_kart` patch also applies sprite palette colors, blur, and special color effects. The force-patch bypasses that body. The Amped renderer has its own player-effect branches, but matching all stock palette, blur, Boo, and hit-effect behavior has not been confirmed by this source/build step; verify those states during native runtime testing before calling racer effects equivalent. The renderer indexes from `0x805ADAC8` by `characterId * 6` and reads three halfwords, so the importer preserves eight raw three-halfword records without assigning them physical labels.

The mod replaces only the project renderer hook. It does not patch or include Amped Up's unrelated gameplay hooks or course/cup assets.

## Wear-report rendering corrections

The v3.21 standard set is selected from its own character-selection data. Z-button
handling at `0x80434C70..0x80434CF8` sets a descriptor cooldown; the tick at
`0x805A4330` advances the selected row and invokes the package loader at
`0x805A4240`. Each `0x805A5D08 + character * 16` descriptor initializes its
selected halfword at `+8` to **2**. Those eight rows have marker 0; the next
Z-selected rows have marker 1 (including subvariants for Yoshi/Toad). The prior
import chose reserved row 0 (`0xFFFE0000`), whose visible models were seasonal.
The current import hydrates the game's normal default row 2 and does not add a
costume-selection menu to retail MK64.

The selector changes only each package's contents at the same destination. It
does not swap the separate skeleton table at `0x805A4740` or animation table at
`0x805A5400`. All 60 typed armature model references must be reached by the final
validated graph. The earlier eight-byte selector walk treated alternating
`ENDDL` records as entries and stopped before the later animated limbs; the
correct sixteen-byte walk covers all nine selectors and rejects an unresolved
vertex in the actual Mario `+0x50` limb at ROM `0x014996C8`. The check is against
private production bytes, not a duplicate test model.


The checked v3.21 code transformations select the original articulated racer plus
character-detail helpers for every visible racer. The primary branch at
`0x805A7490` reaches `0x805A6650` and `0x805A6D30`; the distance route at
`0x805A7738..0x805A7740` reaches the same pair after the existing visibility
rejection. Matrix allocation, alpha, light arguments and player/character indices
remain on their authored paths. This bypasses the absent custom game flags and
race-distance LOD decisions; redirecting the far table to the near table alone
would still leave a reduced model path. Expected-word checks reject other images.

The source star/lightning branch previously read zero-filled custom color rows at
`0x804AC248`; their Amped update hooks are outside the imported renderer. Seven
checked instruction substitutions read the live retail per-player RGB arrays at
`0x80164B10/20/30` instead. The original light/shading construction remains, and
retail `func_800235AC` continues to advance the palette once per game tick. The
renderer neither starts another palette clock nor freezes a chosen star color.
The importer tests execute the actual encoded load and selector blocks for every
player and character, with different palette phases and preserved call arguments.
Native multiple-frame effect images remain a separate acceptance check.

The first full-detail candidate crashed on entering a native race. The newly
reached helper at `0x805A6D30` directly loads an Animation's angle pointer and
writes steering angles before calling stock animation code. Stored segment-0
pointers cannot be used for those CPU accesses. A checked substitution for
`lw a2,12(v0)` (`0x8C46000C`) at `0x805A6F68` calls a local adapter which restores
KSEG0 to the Animation pointer and loaded angle pointer. Its original delay-slot
instruction still executes; the enclosing helper restores its saved return
address. The stored data retains segment-0 encoding for stock traversal.
The animation table spans all 34 entries at `0x805A5400..0x805A5484`, including
steering, effect and podium states; all entries and nested pointers are hydrated.

After `build_mod.py`, run `python3 tools/amped_up/test_animation_runtime.py`.
It compiles the generated helper/adapters and the actual stock recompiled
animation traversal, checks every CPU access, and rejects invalid segment
selectors. Only the matrix conversion functions are observers. It covers
2,192 helper/traversal cases and 19,728 limbs; running the previous generated
helper reproduces its invalid CPU read at `0x005AFCFC`.
The helper scenarios set `gCurrentCourseId` at `0x800DC5A0` and the race/menu
state at `0x800DC510` (the signed offsets following `lui 0x800E`). Assertions
observe the selected animation index: ordinary idle uses character + 1; Amped's
course-20 ceremony route uses character + 18 or + 26 according to player slot.

The corrected private NRM is
`26a3afd600aeb5c6b56857443bb197bd85da633439617a3c17856083d12a02c7`, with hydrated
segment `d36ed4d039d2f9314605a88a65c75812172e33d76a0b99d33a05fb9430a9d3d5`.
Its importer passes 14 checks and both pinned mod compilation tools produce 14
functions. The candidate and selector/import/build provenance are under ignored
`build-linux-vr-validation/wear-fixes/mod/`. These are source/package/host checks;
native all-racer images, star phases and performance are recorded separately below.


## Native checks after wearer feedback

The Frame application built from `f1ee10c450d91fdeb0d79e19c3691e2d00623bb7`
(SHA256 `d8ffc8aacc5d0b88c7fddf68f39f8b0d92e2d073ede72460564081636efc93ec`)
loads the corrected external `26a3afd6…` NRM. A native mixed-field race emitted
all eight distinct characters with full articulated geometry:

| Character | Native triangles | Matrices | Display lists |
| --- | ---: | ---: | ---: |
| Mario | 802 | 14 | 54 |
| Luigi | 732 | 14 | 54 |
| Yoshi | 663 | 14 | 61 |
| Toad | 575 | 14 | 50 |
| Donkey Kong | 657 | 14 | 62 |
| Wario | 737 | 14 | 71 |
| Peach | 633 | 14 | 54 |
| Bowser | 771 | 14 | 54 |

Every traversal reported zero truncation and failure. Earlier native comparisons
used one matrix for Mario/Wario; the new package uses the articulated roots,
including their 173/168-triangle head limbs. These are the author's full N64
meshes, with their original textures. Wario's yellow/purple outfit and Mario's
standard cap/face were inspected in submitted images.

The initial arbitrary-course diagnostic skipped the retail GP grid initialization
on a later cup index, producing duplicated Mario opponents and invalid Bowser
positions. Old and disabled model packages reproduced that failure. The corrected
original debug-course entry initializes the complete roster; native Bowser and
all eight renderers now pass. This diagnostic correction does not change normal
race initialization.

A native Wario star sequence captured normal appearance, several coloured/dithered
active phases, and normal appearance after expiry; live RGB changes were logged
with effect bit `0x200`. A white patch in rear views remained in a private diagnostic
which removed only Mario's 173 head triangles (629 native triangles, 14 matrices).
The patch is exhaust smoke, also identified by the user, rather than head material.
That diagnostic package was
removed and the complete `26a3afd6…` package restored.

Evidence is under ignored `build-linux-vr-validation/wear-fixes/candidate/f1ee10c…/`
and `wear-fixes/diagnostic-head-hidden/`. A separate selector-free 90-second Luigi
Raceway run matched all 68 stock simulation samples and held 120 Hz at 2160×2160
per eye in five settled windows with zero missed periods. See
[performance measurements](FRAME_PERFORMANCE.md). These are unattended captures
with a stationary player; the revised package still needs a worn race retest.

## Additional visual checks

After rebuilding/recompiling the native patches, run:

```sh
python3 tools/amped_up/test_visual_assets.py --kart-source /absolute/path/to/extracted-kart-directory
python3 src/vr/tests/native_visual_assets_test.py
```

These execute graph closure/palette/UV checks and generated native visual hooks, including local-first-person-only gates, inherited material state, authored item scales/colors, and absent/malformed descriptor fallback. Existing importer, generated animation, native item, and host first-person tests cover adjacent behavior. During iteration, transfer the incremental native build promptly and inspect actual first-person/item eyes. Record which colours and poses have device evidence; source checks do not establish rendered or worn acceptance.
