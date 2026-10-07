// The extension's defaults (vr_game_profile_ext.h): DK64's behaviour. Weak, so a game's own
// <game>_profile_ext.c replaces it.
#include "vr_game_profile_ext.h"

static const vr_game_profile_ext default_ext = {
    .perspective_hud_after_camera = 0,
    .takes_comfort_turn = 1,
    .reports_turn_applicability = 0,
    .pause_menu_hud = 0,
    .sky_camera_group = 0,
};

__attribute__((weak)) const vr_game_profile_ext *vr_game_profile_ext_get(void) {
    return &default_ext;
}
