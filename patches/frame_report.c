#include "patches.h"
#include "main.h"
#include "../include/mk64_frame.h"

extern int recomp_mk64_frame_enabled(void);
extern void recomp_mk64_frame(const Mk64Frame* frame);

extern int recomp_mk64_diag_option(int option);
extern void apply_star_sound_effect(Player* player, s8 playerId);

int mk64_diag_racers_enabled;

static void diagnostic_scene(unsigned int frame) {
    static int loaded, character, course, star_at, limit;
    static int selected, star_used;
    static int debug_entry_active, saved_debug_menu;
    if (!loaded) {
        character = recomp_mk64_diag_option(0);
        course = recomp_mk64_diag_option(1);
        star_at = recomp_mk64_diag_option(2);
        limit = recomp_mk64_diag_option(3);
        loaded = 1;
    }
    // An arbitrary GP course needs the native debug-course entry's fresh grid
    // and AI initialization, even when its cup index is not zero. Restore the
    // process-only flag immediately after initialization or an aborted entry.
    if (debug_entry_active && (gGamestate == 4 || gGamestateNext != 4 ||
        limit < 0 || frame > (unsigned int)limit)) {
        gDebugMenuSelection = saved_debug_menu;
        debug_entry_active = 0;
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
            else if (gModeSelection == GRAND_PRIX) {
                saved_debug_menu = gDebugMenuSelection;
                gDebugMenuSelection = DEBUG_MENU_OPTION_SELECTED;
                debug_entry_active = 1;
            }
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
// N64ModernRuntime maps recomp::mem_size = 512 MiB at KSEG0. RT64's
// extended-RDRAM mode accepts these canonical addresses without the 8 MiB mask.
// The top-level span is additionally constrained to the actual active Gfx pool.
#define DIAGNOSTIC_RDRAM_SIZE 0x20000000u
extern Gfx gfxPoolExtended[2][GFX_POOL_SIZE * 0x10];
typedef struct {
    unsigned commands, triangles, matrices, lists, truncated;
    u32 stopped_at, failure;
} RacerDrawStats;
static void diagnostic_stop(RacerDrawStats* stats, u32 address, u32 reason) {
    if (!stats->truncated) { stats->stopped_at = address; stats->failure = reason; }
    stats->truncated = 1;
}
static int diagnostic_address(u32 address) {
    return address >= 0x80000000u && address <= 0x80000000u + DIAGNOSTIC_RDRAM_SIZE - sizeof(Gfx) &&
        !(address & (sizeof(Gfx) - 1));
}
static Gfx* diagnostic_list(u32 address, RacerDrawStats* stats) {
    u32 original = address;
    if (address < 0x10000000u) {
        // Check the segment index before lookup, and the physical base/offset
        // before addition. Never let a malformed base wrap into valid RDRAM.
        u32 base = gSegmentTable[address >> 24];
        u32 offset = address & 0x00FFFFFFu;
        if (base > DIAGNOSTIC_RDRAM_SIZE - sizeof(Gfx) - offset) {
            diagnostic_stop(stats, original, 1);
            return 0;
        }
        address = 0x80000000u + base + offset;
    }
    if (!diagnostic_address(address)) {
        diagnostic_stop(stats, original, 1);
        return 0;
    }
    return (Gfx*)address;
}
static void diagnostic_walk(Gfx* list, Gfx* end, unsigned depth, RacerDrawStats* stats) {
    if (!list) { diagnostic_stop(stats, 0, 1); return; }
    if (depth > 16) { diagnostic_stop(stats, (u32)list, 2); return; }
    while ((!end || list < end) && stats->commands < 8192) {
        if (!diagnostic_address((u32)list)) { diagnostic_stop(stats, (u32)list, 1); return; }
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
            diagnostic_walk(diagnostic_list(w1, stats), 0, depth + 1, stats);
            if (stats->truncated) return;
            if ((w0 >> 16) & 1) return; // G_DL_NOPUSH tail branch
        }
    }
    if (stats->commands >= 8192) diagnostic_stop(stats, (u32)list, 3);
}
static void diagnostic_racer_span(Gfx* begin, Gfx* end, RacerDrawStats* stats) {
    Gfx* pool = gfxPoolExtended[gGlobalTimer & 1];
    u32 first = (u32)begin, last = (u32)end;
    if (first < (u32)pool || last > (u32)(pool + GFX_POOL_SIZE * 0x10) ||
        first > last || (first & 7) || (last & 7)) {
        diagnostic_stop(stats, first, 4);
        return;
    }
    diagnostic_walk(begin, end, 0, stats);
}
void mk64_diag_racer(Player* player, int playerId, Gfx* begin, Gfx* end) {
    RacerDrawStats stats = {0};
    diagnostic_racer_span(begin, end, &stats);
    s16* rgb = (s16*)0x80164B10;
    recomp_printf("[mk64-diag] racer player=%d character=%d effects=%08x commands=%u triangles=%u matrices=%u lists=%u truncated=%u rgb=%d,%d,%d begin=%08x end=%08x stopped_at=%08x failure=%u\n",
        playerId, player->characterId, player->effects, stats.commands, stats.triangles,
        stats.matrices, stats.lists, stats.truncated, rgb[playerId], rgb[8 + playerId], rgb[16 + playerId],
        (u32)begin, (u32)end, stats.stopped_at, stats.failure);
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
