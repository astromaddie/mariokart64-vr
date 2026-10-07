// Per-game facts the VR renderer needs (frozen interface; change only by agreement).
//
// The game side (src/vr/game/*_profile.c) defines vr_game_profile_get(). The renderer and the
// settings use it instead of game-specific constants, so the same VR layer serves DK64 and Banjo.
#ifndef VR_GAME_PROFILE_H
#define VR_GAME_PROFILE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct vr_game_profile {
    // RT64 extended-GBI matrix group ids (gEXMatrixGroup on G_MTX_PROJECTION) that tag the world
    // camera's perspective projection, most specific first. The renderer replaces the view and
    // projection of a perspective projection carrying one of these ids with the eye's, falling
    // back to any perspective projection drawn into the main colour image.
    const uint32_t *camera_matrix_groups;
    int camera_matrix_group_count;
    // Height of the player character's model in game units, used to present world_scale as
    // "<player> height in metres" and to choose the default scale.
    float player_height_units;
    // Default world_scale (game units per metre) that makes the player life-size.
    float default_world_scale;
    // The near plane the game's camera uses, in game units (for logs and the fog remap check).
    float game_near_units;
    // Display name of the player for UI text, e.g. "DK" or "Banjo".
    const char *player_name;
} vr_game_profile;

const vr_game_profile *vr_game_profile_get(void);

#ifdef __cplusplus
}
#endif

#endif
