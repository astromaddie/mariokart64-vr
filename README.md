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

## Build and install

You don't need a Mac. The Docker script builds the same **Linux ARM64 Frame package** from these hosts:

| Build machine | Route |
| --- | --- |
| Frame Desktop or another ARM64 Linux machine | Docker Engine; native ARM64 build |
| Windows PC | WSL2 Ubuntu + Docker Desktop, with WSL integration enabled |
| macOS, Apple Silicon or Intel | Docker Desktop, or an ARM64-capable Docker environment |
| x86_64 Linux PC | Docker Engine with ARM64 emulation configured |

On x86_64 computers the compiler runs under ARM64 emulation, which can be much slower. You'll need Bash, Git, Python 3 and `shasum` on the host as well as a running Docker engine. [BUILDING.md](BUILDING.md) covers setup, building on Frame Desktop, first installation and Windows paths.

Build the Frame version with your own supported US ROM:

```sh
git clone --recurse-submodules --branch main https://github.com/astromaddie/mariokart64-vr.git
cd mariokart64-vr
export MK64_ROM="/path/to/owned-us-rom.z64"
MK64_VR=ON JOBS=4 tools/docker/build-linux.sh all
```

The result is `build-linux-aarch64/package/MarioKart64Recompiled/`. On Frame Desktop, copy that whole folder somewhere permanent and add `LAUNCH-STEAM-FRAME.sh` to Steam with launch options `--game mk64`. From another computer, upload that folder with Valve's SteamOS Devkit Client using the Linux ARM64 runtime. Keep your ROM at `~/.local/share/MK64FrameVR/mk64.us.z64` on the Frame. Launch from the Frame's Steam library so SteamVR supplies controller input.

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
