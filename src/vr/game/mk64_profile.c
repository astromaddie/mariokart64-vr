#include "vr_game_profile.h"
#include "vr_game_profile_ext.h"

static const unsigned int camera_groups[] = { 0xFFFFAAAAu, 0xFFFFAAE0u };
// Calibration starting point, not a physical measurement: 10 game units/metre.
// The retained stock chase camera and world_scale setting make this reversible.
static const vr_game_profile profile = { camera_groups, 2, 10.0f, 10.0f, 9.0f, "Kart reference" };
static const vr_billboard_group billboard_groups[] = {
    { 0x20000000u, 0x2000FFFFu, VR_BILLBOARD_CYLINDRICAL },
    { 0x60000000u, 0x62FFFFFFu, VR_BILLBOARD_CYLINDRICAL },
};
static const vr_game_profile_ext extension = {
    .perspective_hud_after_camera = 1,
    .takes_comfort_turn = 0,
    .reports_turn_applicability = 0,
    .billboard_groups = billboard_groups,
    .billboard_group_count = 2,
    .pause_menu_hud = 0,
    .sky_camera_group = 0xFFFFAAE0u,
};
const vr_game_profile* vr_game_profile_get(void) { return &profile; }
const vr_game_profile_ext* vr_game_profile_ext_get(void) { return &extension; }
