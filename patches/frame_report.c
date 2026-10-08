#include "patches.h"
#include "main.h"
#include "../include/mk64_frame.h"

extern int recomp_mk64_frame_enabled(void);
extern void* segmented_to_virtual(const void* address);
extern void recomp_mk64_frame(const Mk64Frame* frame);

extern int recomp_mk64_diag_option(int option);
extern void apply_star_sound_effect(Player* player, s8 playerId);

int mk64_diag_racers_enabled;

static void diagnostic_scene(unsigned int frame) {
    static int loaded, character, course, star_at, limit;
    static int selected, star_used;
    if (!loaded) {
        character = recomp_mk64_diag_option(0);
        course = recomp_mk64_diag_option(1);
        star_at = recomp_mk64_diag_option(2);
        limit = recomp_mk64_diag_option(3);
        loaded = 1;
    }
    mk64_diag_racers_enabled = limit >= 0 && frame <= (unsigned int)limit &&
        gGamestate == 4 && !gDemoMode && gCourseTimer > 0.0f && (frame % 30) == 0;
    if (limit < 0 || frame > (unsigned int)limit) return;
    // thread5 applies gGamestateNext and calls update_gamestate at the NEXT
    // iteration, after this end-of-display-list boundary. Change the selection
    // before native course loading/player spawn, never a live racer's identity.
    if (!selected && gGamestate != 4 && gGamestateNext == 4 && !gDemoMode) {
        if (character >= 0) gCharacterSelections[0] = character;
        if (course >= 0) {
            int found = 0;
            for (int cup = 0; cup < 4; ++cup) {
                for (int index = 0; index < 4; ++index) {
                    if (gCupCourseOrder[cup][index] == course) {
                        found = 1;
                        gCupSelection = cup;
                        gCourseIndexInCup = index;
                        gCurrentCourseId = course;
                    }
                }
            }
            if (!found) recomp_printf("[mk64-diag] rejected course=%d: requires a retail Grand Prix course\n", course);
        }
        selected = 1;
        if (character >= 0 || course >= 0)
            recomp_printf("[mk64-diag] selection character=%d course=%d cup=%d index=%d frame=%u\n",
                gCharacterSelections[0], gCurrentCourseId, gCupSelection, gCourseIndexInCup, frame);
    }
    if (!star_used && star_at >= 0 && gGamestate == 4 && gActiveScreenMode == 0 &&
        !gDemoMode && !gIsGamePaused && gCourseTimer >= (float)star_at && gCourseTimer > 0.0f) {
        apply_star_sound_effect(&gPlayers[0], 0);
        star_used = 1;
        recomp_printf("[mk64-diag] star via native item effect character=%d course=%d frame=%u\n",
            gPlayers[0].characterId, gCurrentCourseId, frame);
    }
}

// A bounded walk of the actual display lists emitted by render_kart. It runs
// once per second only during an explicitly requested autostart diagnostic.
// Stop on unresolved pointers/depth/budget, and report truncation rather than
// treating a partial walk as an authoritative primitive count.
typedef struct { unsigned commands, triangles, matrices, lists, truncated; } RacerDrawStats;
static Gfx* diagnostic_list(u32 address) {
    if (address < 0x10000000u) {
        address = (u32)segmented_to_virtual((void*)address);
    }
    if (address < 0x80000000u || address > 0x807FFFF8u || (address & 7)) return 0;
    return (Gfx*)address;
}
static void diagnostic_walk(Gfx* list, Gfx* end, unsigned depth, RacerDrawStats* stats) {
    if (!list || depth > 16) { stats->truncated = 1; return; }
    while ((!end || list < end) && stats->commands < 8192) {
        if ((u32)list > 0x807FFFF8u) { stats->truncated = 1; return; }
        u32 w0 = list->words.w0, w1 = list->words.w1;
        unsigned op = w0 >> 24;
        ++list;
        ++stats->commands;
        if (op == 0xB8) return; // F3DEX ENDDL
        if (op == 0xBF) ++stats->triangles;
        if (op == 0xB1) stats->triangles += 2;
        if (op == 0x01) ++stats->matrices;
        if (op == 0x06) {
            ++stats->lists;
            diagnostic_walk(diagnostic_list(w1), 0, depth + 1, stats);
            if ((w0 >> 16) & 1) return; // G_DL_NOPUSH tail branch
        }
    }
    if (stats->commands >= 8192) stats->truncated = 1;
}
void mk64_diag_racer(Player* player, int playerId, Gfx* begin, Gfx* end) {
    RacerDrawStats stats = {0};
    diagnostic_walk(begin, end, 0, &stats);
    s16* rgb = (s16*)0x80164B10;
    recomp_printf("[mk64-diag] racer player=%d character=%d effects=%08x commands=%u triangles=%u matrices=%u lists=%u truncated=%u rgb=%d,%d,%d\n",
        playerId, player->characterId, player->effects, stats.commands, stats.triangles,
        stats.matrices, stats.lists, stats.truncated, rgb[playerId], rgb[8 + playerId], rgb[16 + playerId]);
}

// Once per completed game display list, never per eye or RT64 interpolation frame.
RECOMP_PATCH void end_master_display_list(void) {
    if (recomp_mk64_frame_enabled()) {
        static unsigned int frame_number;
        Mk64Frame state;
        Camera* camera = &cameras[0];
        state.frame = ++frame_number;
        diagnostic_scene(frame_number);
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
