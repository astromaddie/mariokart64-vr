# PR0 release-readiness record — Mario Kart 64 VR

**State: EXPERIMENTAL; no public Steam Frame build or release.** Source, device and wearer evidence are distinguished below.

## Identity and target

- Upstream: [sonicdcer/MarioKart64Recomp](https://gitlab.com/sonicdcer/MarioKart64Recomp).
- Target: standalone Steam Frame, Linux ARM64, SteamVR/OpenXR, Vulkan via SDL2, RT64 and Plume.
- Source baseline before PR0 edits: `c4b901a04f96b264a0ac710d210a627e238b3e79`.
- Tested source: baseline plus the PR0 working-tree change set on 2026-10-11; final integrated commit ID is pending coordinator integration.
- Intended runtime target: Steam Frame standalone, Linux ARM64, SteamVR/OpenXR and Vulkan; experimental, with no general platform-support claim.
- Host validation: macOS ARM64; the public workflow is configured for Ubuntu 22.04 but has not yet produced a remote GitHub run.
- RT64 public base: `43373749dac9bbc1b653e6a02aed40a9e1783bed`; VR overlay SHA-256: `31c47db5fe78ea63272cf824d4b3f2ac738f04577081749e557e756cbfd0fcf7`.
- Plume public base: `d890ac899e505fb30040e037a4037cdeca68f033`; VR overlay SHA-256: `99fbdb9731416e35cbc5854bf977cf8fc3679655246462f6e6fed145d18294db`.

The bootstrap checks exact base commits and patch hashes, then applies tracked VR source overlays to clean public checkouts. It keeps RT64 and Plume license/notice files intact and removes the private submodule URLs.

## Evidence

- **Host/source:** ROM-free production VR bridge/profile/first-person/diagnostic CMake/CTest plus RT64 eye-slot and source-contract tests: 8/8 passed on 2026-10-11 in a fresh macOS ARM64 checkout with an empty HOME and no Git credentials.
  ```sh
  bash tools/vr/prepare-public-dependencies.sh
  cmake -S src/vr/tests -B build-vrtest -G Ninja
  cmake --build build-vrtest --parallel 2
  ctest --test-dir build-vrtest --output-on-failure
  ```
- **Public CI:** Configured for GitHub push/PR with no repository secrets or ROM; its remote GitHub run has not yet been observed. The [workflow](../.github/workflows/public-vr-validation.yml) fetches public sources and runs CMake/CTest.
- **Unattended Frame:** Earlier off-head builds verified OpenXR stereo submission, gameplay captures and simulation parity. A previous full-detail package passed 120 Hz sampling without missed predicted periods; that evidence does not cover the newer cockpit/item paths.
- **Worn:** The user completed a race on a predecessor build and reported rendering issues. The revised source/package has not passed wearer retest; full-course coverage remains pending.
- **Performance:** historical off-head measurements are in [Frame performance](FRAME_PERFORMANCE.md). Current-source worn performance, including the new cockpit/items, is unmeasured.

## Clean-checkout boundary

The clean host run used the source baseline plus the PR0 working-tree change set listed above; the final integrated commit ID is pending coordinator integration. Each checkout used a separate empty HOME, disabled system/global Git configuration, no SSH agent or GitHub token, and fetched only public sources.

The ROM-free test path initialized public RT64/Plume and their pinned overlays plus runtime/MK64 sources used by production source-contract tests. It compiled production VR code and passed CTest 8/8. This is source/test evidence on macOS ARM64, not a full runtime support claim. The GitHub workflow is configured for Ubuntu 22.04 but has not yet produced a remote run.

The tests do not build the full game executable or native package.

A complete build and playable run require the owned local supported US ROM. Optional Amped Up use also requires the official v3.21 patch and generated model NRM. None was copied here or used by CI; no complete application build is claimed.

## External data and full build

The ROM, official patch and generated NRM are local external inputs, excluded from source and CI artifacts. Use only data you own and keep it outside the public tree.

```sh
MK64_ROM="/path/to/owned-us-rom.z64" MK64_VR=ON JOBS=4 tools/docker/build-linux.sh all
```

See [VR architecture](VR_ARCHITECTURE.md) for implementation, prior device evidence, limitations and the wearer checklist.

## Legacy upstream CI

The inherited full-build workflows fetch private data and are disabled by default in this fork. To opt in deliberately, set the repository Actions variable `RUN_LEGACY_VALIDATION` to the exact string `true` and configure the required repository secrets: `MK64_REPO_WITH_PAT` (private ROM-data repository) and `MK64_TOKEN`. The automatic `public-vr-validation` workflow is independent and requires no secrets or ROM.
