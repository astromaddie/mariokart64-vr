#include "patches.h"
#include "main.h"
#include "../include/mk64_frame.h"

extern int recomp_mk64_frame_enabled(void);
extern void recomp_mk64_frame(const Mk64Frame* frame);

// Once per completed game display list, never per eye or RT64 interpolation frame.
RECOMP_PATCH void end_master_display_list(void) {
    if (recomp_mk64_frame_enabled()) {
        static unsigned int frame_number;
        Mk64Frame state;
        Camera* camera = &cameras[0];
        state.frame = ++frame_number;
        state.game_state = gGamestate;
        state.screen_mode = gActiveScreenMode;
        state.demo = gDemoMode;
        state.paused = gIsGamePaused;
        state.course = gCurrentCourseId;
        state.global_timer = gGlobalTimer;
        state.race_time = gCourseTimer;
        for (int axis = 0; axis < 3; ++axis) {
            state.eye[axis] = camera->pos[axis];
            state.at[axis] = camera->lookAt[axis];
            state.up[axis] = camera->up[axis];
        }
        state.fov = gCameraZoom[0];
        state.near_z = gCourseNearPersp;
        state.far_z = gCourseFarPersp;
        for (int i = 0; i < 8; ++i) {
            for (int axis = 0; axis < 3; ++axis) state.player_pos[i][axis] = gPlayers[i].pos[axis];
            state.player_speed[i] = gPlayers[i].currentSpeed;
            state.player_lap[i] = gLapCountByPlayerId[i];
            state.player_rank[i] = gPlayers[i].currentRank;
        }
        recomp_mk64_frame(&state);
    }
    gDPFullSync(gDisplayListHead++);
    gSPEndDisplayList(gDisplayListHead++);
    create_gfx_task_structure();
}
