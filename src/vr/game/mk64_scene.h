#pragma once
#include "mk64_frame.h"
#include "dk64vr_game_state.h"
inline dk64vr_scene mk64_vr_scene(const Mk64Frame& state) {
    return state.game_state != 4 ? DK64VR_SCENE_MENU :
        state.screen_mode != 0 ? DK64VR_SCENE_MULTIPLAYER :
        state.demo ? DK64VR_SCENE_CUTSCENE :
        state.paused ? DK64VR_SCENE_PAUSE :
        // The native race intro animates a letterboxed viewport and a scripted camera.
        state.race_time <= 0.0f ? DK64VR_SCENE_CUTSCENE : DK64VR_SCENE_GAMEPLAY;
}
