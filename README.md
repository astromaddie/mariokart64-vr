# Mario Kart 64 VR for Steam Frame

This is my Steam Frame fork of [Mario Kart 64 Recompiled](https://gitlab.com/sonicdcer/MarioKart64Recomp). It adds native OpenXR stereo play to the Linux ARM64 game, using SteamVR, Vulkan, RT64 and Plume. Flat mode remains available.

**EXPERIMENTAL.** This is a personal-use project and is still a work in progress. You need a supported US Mario Kart 64 ROM from your own copy of the game. Optional Amped Up content also needs the official v3.21 patch and a generated NRM. The ROM, patch and generated game data are not included.

## What the Frame fork adds

- Tracked stereo racing, with menus and the HUD presented on panels and race scenes in the 3D view.
- A seated first-person kart view with a cockpit, visible arms and a grip-operated steering wheel. Steering remains tied to the kart when you look around; releasing both grips returns steering to the left stick.
- Optional over-shoulder item handling. Hold an item beside either shoulder and throw with a backward arm swing; forward and rear throws follow the item's game behavior.
- A quick first-person/chase-view toggle on View. Hold View to recenter without switching views.
- Steam Frame controls and a native Linux ARM64 build and install path. Without an active OpenXR runtime the game runs flat.

The first-person controls and renderer integration are described in [VR architecture](docs/VR_ARCHITECTURE.md). See [Amped Up data requirements](docs/AMPED_UP.md) for the optional patch and model data, and [Frame performance notes](docs/FRAME_PERFORMANCE.md) for recorded measurements and their scope.

## Build

Use Docker on ARM64 Linux or an ARM64 Docker environment on Apple Silicon. The build script creates its pinned compiler image and packages the game.

Build the Frame version with your own supported US ROM:

```sh
git clone --recurse-submodules --branch main https://github.com/astromaddie/mariokart64-vr.git
cd mariokart64-vr
export MK64_ROM="/path/to/owned-us-rom.z64"
MK64_VR=ON JOBS=4 tools/docker/build-linux.sh all
```

The Frame package and generated game data stay outside Git. See [BUILDING.md](BUILDING.md) for prerequisites, build steps, and installation details.

To update the existing `MarioKart64VR` Steam entry, copy the package and your own ROM to the Frame:

```sh
export FRAME_HOST="steamos@YOUR_FRAME_ADDRESS"
ssh "$FRAME_HOST" 'mkdir -p ~/devkit-game/MarioKart64VR ~/.local/share/MK64FrameVR'
rsync -a --delete build-linux-aarch64/package/MarioKart64Recompiled/ \
  "$FRAME_HOST:devkit-game/MarioKart64VR/"
rsync -a "$MK64_ROM" "$FRAME_HOST:.local/share/MK64FrameVR/mk64.us.z64"
```

Then launch `MarioKart64VR` from the Frame's Steam library so SteamVR supplies controller input.

## ROM-free VR checks

The [VR validation workflow](.github/workflows/public-vr-validation.yml) runs without a ROM or repository secrets. You can run the same production-source checks locally after cloning the dependencies above, with CMake, Ninja and a C++ compiler:

```sh
bash tools/vr/prepare-public-dependencies.sh
cmake -S src/vr/tests -B build-vrtest -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-vrtest
ctest --test-dir build-vrtest --output-on-failure
```

## Upstream and licenses

The fork retains Mario Kart 64 Recompiled's upstream notices and license. The earlier [PR0 readiness audit](docs/PR0_READINESS.md), [source and CI metadata](docs/PR0_METADATA.json), and [README history](docs/README_PRE_PR0.md) remain available as historical records. The host application retains its upstream [GPLv3 notice](COPYING); RT64 and Plume retain their own MIT notices. Code licenses do not grant permission to redistribute the commercial game, ROMs or extracted media. Bring your own game data.
