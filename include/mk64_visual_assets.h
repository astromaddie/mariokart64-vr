#ifndef MK64_VISUAL_ASSETS_H
#define MK64_VISUAL_ASSETS_H
/* Private mod trailer, beyond the frontend startup framebuffer range. Older or
 * absent mods have no matching descriptor and keep the existing visual path. */
#define MK64_VISUAL_ASSET_ADDRESS 0x80750000u
#define MK64_VISUAL_ASSET_MAGIC 0x4D4B5652u
#define MK64_VISUAL_ASSET_VERSION 2u
#define MK64_SOLID_ITEM_GROUP 0x76000000u
#define MK64_COCKPIT_GROUP 0x75000000u
#define MK64_SHELL_GROUP 0x74000001u
#define MK64_BANANA_GROUP 0x74000002u
#define MK64_VISUAL_ITEMS 1u
#define MK64_VISUAL_COCKPIT 2u
typedef struct Mk64VisualAssets {
    unsigned magic, version, flags, end;
    unsigned cockpit[8];
    unsigned wheel, reserved;
} Mk64VisualAssets;
#endif
