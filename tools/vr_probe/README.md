# Mario Kart 64 Steam Frame native OpenXR probe

This standalone ARM64 Linux executable tests the SteamVR/OpenXR Vulkan contract with two independent `PRIMARY_STEREO` eyes. It uses `XR_KHR_vulkan_enable2`, a runtime-created Vulkan instance and device, runtime-selected physical device, `XR_REFERENCE_SPACE_TYPE_LOCAL`, predicted display time, sRGB swapchain images with mutable UNORM image views, and per-eye acquire/wait/clear/submit/release handling. Each clear uses a Vulkan framebuffer backed by the UNORM view and returns the swapchain image to `VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL`. Left and right use distinct red- and blue-dominant clears. It exits nonzero if it cannot submit a valid stereo frame before the finite duration expires, then requests orderly session exit.

Run as `./mk64-frame-probe --seconds 30` (the default duration is 30 seconds). A passing run prints runtime, system, GPU, eye sizes, session-state transitions, and the number of submitted stereo frames.

Build inside the `dk64-vr-linux:latest` ARM64 container with `./build.sh`. The script links `/opt/openxr/lib/libopenxr_loader.a` statically and the image's system Vulkan library dynamically. The resulting binary targets Ubuntu 22.04 / glibc 2.35 and contains no copied GPU driver.

The container build succeeded. The no-runtime check used `XR_RUNTIME_JSON=/tmp/no-openxr-runtime.json ./mk64-frame-probe --seconds 1`; the loader could not find a runtime, the probe exited 1, and it reported zero submitted frames. This only verifies its failure path; actual headset rendering remains unverified.

Binary SHA-256: `f6dfa0ad605072ee9f77eff13b3d3123fc54d9c7981bc7a212ecb8c1bf8a197f`

On 2026-10-07, this binary launched through the Frame Steam library and passed on SteamVR/OpenXR 2.17.10 with a Turnip Adreno 750. It submitted one valid stereo frame with two 1728x1728 eyes while the unworn device was in SYNCHRONIZED. Eye colors and sustained rendering still need a worn check.

For Docker contexts that do not share macOS `/tmp`, copy this directory into a temporary container with `docker cp`, run `build.sh` there, then copy the executable back. The device-tested binary above used that method with image `sha256:6cd15fa7941a706358920701a1ccb504852e8ebf1df6ebb0f4b92de6814455f4`.
