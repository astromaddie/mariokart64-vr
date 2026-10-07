#include <cassert>
#include <cmath>
#include "../game/mk64_scene.h"
#include "vr_game_profile.h"
#include "vr_game_profile_ext.h"
#include "dk64vr_input.h"
#include "dk64vr_settings.h"
int main() {
    Mk64Frame state{};
    assert(mk64_vr_scene(state) == DK64VR_SCENE_MENU);
    state.game_state = 4;
    assert(mk64_vr_scene(state) == DK64VR_SCENE_CUTSCENE);
    state.race_time = 1.0f / 30.0f;
    assert(mk64_vr_scene(state) == DK64VR_SCENE_GAMEPLAY);
    state.paused = 1;
    assert(mk64_vr_scene(state) == DK64VR_SCENE_PAUSE);
    state.demo = 1;
    assert(mk64_vr_scene(state) == DK64VR_SCENE_CUTSCENE);
    state.screen_mode = 1;
    assert(mk64_vr_scene(state) == DK64VR_SCENE_MULTIPLAYER);
    state.screen_mode = state.demo = 0;
    state.race_time = 0;
    assert(mk64_vr_scene(state) == DK64VR_SCENE_PAUSE);
    const auto* profile = vr_game_profile_get();
    assert(profile->camera_matrix_group_count == 2);
    assert(profile->camera_matrix_groups[0] == 0xFFFFAAAA);
    assert(vr_game_profile_ext_get()->sky_camera_group == profile->camera_matrix_groups[1]);
    assert(vr_game_profile_ext_get()->perspective_hud_after_camera);
    dk64vr_settings_t settings{};
    dk64vr_settings_defaults(&settings);
    assert(dk64vr_settings_get(&settings, "move_from_view") == 0);
    assert(dk64vr_settings_get(&settings, "turn_mode") == 2);
    assert(dk64vr_settings_get(&settings, "resolution_scale") == 1);
    assert(dk64vr_settings_get(&settings, "level_pitch") == 0);
    assert(dk64vr_settings_get(&settings, "eye_near_m") == 0.05);
    assert(dk64vr_settings_get(&settings, "world_scale") == profile->default_world_scale);
    dk64vr_settings_free(&settings);
    dk64vr::InputConfig config;
    config.moveFromView = false;
    config.turnMode = dk64vr::TurnMode::Off;
    config.rightStickX = dk64vr::RightStickX::GameCamera;
    dk64vr::InputContext context;
    context.stereoPlay = true;
    dk64vr::InputSample sample;
    sample.valid = true;
    dk64vr::InputMapper mapper;
    mapper.update(sample, config, context, 0, .014f);
    sample.lBumper = sample.rBumper = sample.lStickClick = sample.rStickClick = true;
    sample.lStick[0] = 1;
    auto result = mapper.update(sample, config, context, .014, .014f);
    assert((result.buttons & (dk64vr::n64::Z | dk64vr::n64::R | dk64vr::n64::L | dk64vr::n64::CUp)) ==
        (dk64vr::n64::Z | dk64vr::n64::R | dk64vr::n64::L | dk64vr::n64::CUp));
    context.viewYawRad = 3.14159265f;
    auto turned = mapper.update(sample, config, context, .028, .014f);
    assert(std::fabs(result.stickX - turned.stickX) < 1e-6f && std::fabs(turned.stickY) < 1e-6f);
    sample.valid = false;
    assert(mapper.update(sample, config, context, .042, .014f).buttons == 0);
}
