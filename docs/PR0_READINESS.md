# PR0 — mariokart64-vr

**EXPERIMENTAL — public source.** Based on [sonicdcer/MarioKart64Recomp](https://gitlab.com/sonicdcer/MarioKart64Recomp), targeting native Linux ARM64 Steam Frame, SteamVR/OpenXR and Vulkan. No binary release was uploaded.

At `ecd49d581b984ebd3e587572c5fbac58b94f8d1b`, the ROM-free production VR CMake/CTest suite passed 8/8 from a clean checkout with an empty home and no personal Git credentials. Public RT64/Plume bases and the hash-pinned VR overlays resolved correctly. The complete ARM64 application, package, ABI check and 30-second Xvfb launch smoke also passed. The package has 43 files and no ROM files; its binary hash is recorded in the metadata.

The automatic [public validation workflow](../.github/workflows/public-vr-validation.yml) uses no ROMs or repository secrets. The [current public CI run](https://github.com/astromaddie/mariokart64-vr/actions/runs/38122892712) passed, including checkout, dependency setup, compilation and tests. Earlier CI results remain in [PR0_METADATA.json](PR0_METADATA.json).

The history audit found no ROMs, extracted game-data payloads or personal credentials. Project branding and gameplay captures remain separate from the source licenses. Upstream GPLv3 host notices in `COPYING` and renderer/component notices are preserved; they do not give permission to distribute Nintendo's game or data.

For the ROM-free checks, run:

```sh
bash tools/vr/prepare-public-dependencies.sh
cmake -S src/vr/tests -B build-vrtest -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-vrtest --parallel 2
ctest --test-dir build-vrtest --output-on-failure
```

The full build takes your own game input: `MK64_ROM=/path/to/owned-rom.z64 MK64_VR=ON JOBS=4 tools/docker/build-linux.sh all`. The README and architecture documentation list the supported revision and current features. Inherited workflows that need private data remain disabled unless `RUN_LEGACY_VALIDATION=true` and their required secrets are configured.
