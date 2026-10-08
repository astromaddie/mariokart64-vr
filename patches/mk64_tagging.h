#ifndef MK64_TAGGING
#define MK64_TAGGING

#define TAG_ITEM_ADDR(x) ((u32) 0x10000000 | (u32) x)
#define TAG_SMOKE_DUST(x) ((u32) 0x20000000 | (u32) (x))
#define TAG_LETTER(x) ((u32) 0x30000000 | (u32) (x))
#define TAG_OBJECT(x) ((u32) 0x40000000 | (u32) (x))
#define TAG_OBJECT_BY_CAM_ID(x) ((u32) 0x50000000 | (u32) (x << 16))
// Dedicated sprite-only ranges. Never tag a parent containing shadows/models.
#define TAG_WORLD_SPRITE(x) (0x60000000u | ((u32)(x) & 0x00FFFFFFu))
#define TAG_WORLD_ACTOR(x) (0x61000000u | ((u32)(x) & 0x00FFFFFFu))
#endif