#include <atomic>
#include <array>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "recomp.h"
#include "librecomp/helpers.hpp"
#include "mk64_frame.h"
#include "mk64_first_person.h"

#ifdef MK64_VR
#include <mutex>
#include <thread>
#include "dk64vr_game_state.h"
#include "dk64vr_control.h"
#include "../vr/game/mk64_scene.h"
namespace {
constexpr size_t kWords = sizeof(dk64vr_game_state) / sizeof(uint32_t);
std::atomic<uint32_t> sequence{0};
std::atomic<uint32_t> snapshot[kWords]{};
std::mutex writer_mutex;
std::mutex interaction_mutex;
Mk64VRInteraction interaction{};
Mk64Frame racer{};
unsigned interaction_serial = 0;
std::atomic<int> active{0};
std::atomic<int> render_yaw{0};
std::atomic<int> diag_save_in_play{0};

bool force_patches() {
    static const bool forced = [] {
        const char *value = std::getenv("MK64_VR_FORCE_PATCHES");
        return value && value[0] && value[0] != '0';
    }();
    return forced;
}
}

extern "C" void mk64_vr_publish_interaction(const Mk64VRInteraction* state) {
    std::lock_guard<std::mutex> lock(interaction_mutex);
    // Keep one edge until the simulation consumes it; display frames cannot overwrite it.
    const int command = interaction.command;
    const int rear = interaction.rear;
    float velocity[3]; std::memcpy(velocity, interaction.velocity, sizeof velocity);
    interaction = *state;
    if (command && !state->command && state->enabled) { interaction.command=command; interaction.rear=rear; std::memcpy(interaction.velocity,velocity,sizeof velocity); }
    interaction.serial = ++interaction_serial;
}
extern "C" void mk64_vr_get_racer(Mk64Frame* state) {
    std::lock_guard<std::mutex> lock(interaction_mutex); *state=racer;
}
extern "C" void recomp_mk64_vr_interaction(uint8_t* rdram, recomp_context* ctx) {
    std::lock_guard<std::mutex> lock(interaction_mutex);
    std::memcpy(_arg<0, Mk64VRInteraction*>(rdram, ctx), &interaction, sizeof interaction);
    interaction.command=0;
}
extern "C" void dk64vr_publish_game_state(const dk64vr_game_state *state) {
    if (!state) return;
    uint32_t words[kWords];
    std::memcpy(words, state, sizeof(words));
    std::lock_guard<std::mutex> lock(writer_mutex);
    // Sequentially consistent atomic words make the seqlock well-defined in C++ even
    // during concurrent copies. A reader accepts only one complete, even generation.
    sequence.fetch_add(1);
    for (size_t i = 0; i < kWords; ++i) snapshot[i].store(words[i]);
    sequence.fetch_add(1);
}

extern "C" void dk64vr_get_game_state(dk64vr_game_state *out) {
    if (!out) return;
    uint32_t words[kWords];
    for (;;) {
        const uint32_t before = sequence.load();
        if (before & 1) continue;
        for (size_t i = 0; i < kWords; ++i) words[i] = snapshot[i].load();
        if (sequence.load() == before) break;
    }
    std::memcpy(out, words, sizeof(words));
}

extern "C" int dk64vr_is_active(void) {
    return active.load(std::memory_order_relaxed) || force_patches();
}
extern "C" void mk64_vr_set_yaw(float radians) { render_yaw.store(int(radians * (65536.0f / 6.283185307f))); }
extern "C" void recomp_mk64_vr_yaw(uint8_t*, recomp_context* ctx) { _return(ctx, render_yaw.load()); }
extern "C" void dk64vr_set_active(int value) {
    active.store(value != 0, std::memory_order_relaxed);
    if (!value) dk64vr_clear_turn();
}
extern "C" void dk64vr_set_diag_save_in_play(int enabled) {
    diag_save_in_play.store(enabled != 0, std::memory_order_relaxed);
}
extern "C" int dk64vr_diag_save_in_play(void) {
    return diag_save_in_play.load(std::memory_order_relaxed);
}
// The runtime's quit flag (librecomp/src/recomp.cpp), so a paused game never holds up a quit.
extern std::atomic_bool exited;

extern "C" void recomp_vr_is_active(uint8_t *rdram, recomp_context *ctx) {
    (void)rdram;
    _return(ctx, dk64vr_is_active());
}
#endif
#ifndef MK64_VR
extern "C" void recomp_mk64_vr_interaction(uint8_t* rdram, recomp_context* ctx) {
    Mk64VRInteraction empty{}; std::memcpy(_arg<0, Mk64VRInteraction*>(rdram, ctx), &empty, sizeof empty);
}
extern "C" void recomp_mk64_vr_yaw(uint8_t*, recomp_context* ctx) { _return(ctx, 0); }
extern "C" void recomp_vr_is_active(uint8_t*, recomp_context* ctx) { _return(ctx, 0); }
#endif
static_assert(sizeof(Mk64Frame) == 292, "MIPS/native frame ABI");
namespace {
std::atomic<bool> in_race{false};
std::atomic<unsigned> game_frame{0};
std::atomic<unsigned long long> vi_count{0}, audio_samples{0}, rumble_calls{0};
int diagnostic_interval() {
    static const int interval = [] {
        const char* value = std::getenv("MK64_DIAG_FRAMES");
        return value ? std::max(0, std::atoi(value)) : 0;
    }();
    return interval;
}
}
void mk64_count_vi() { ++vi_count; }
void mk64_count_audio(unsigned samples) { audio_samples += samples; }
void mk64_count_rumble() { ++rumble_calls; }
bool mk64_diag_input(int player, uint16_t* buttons, float*, float*) {
    static const int seconds = [] {
        const char* value = std::getenv("MK64_DIAG_AUTOSTART");
        return value ? std::clamp(std::atoi(value), 0, 120) : 0;
    }();
    if (player != 0 || !seconds) return false;
    static bool done = false;
    if (done) return false;
    const unsigned frame = game_frame.load();
    if (in_race.load() || frame >= unsigned(seconds) * 30u) {
        done = true;
        printf("[mk64-diag] autostart stopped: %s at frame=%u\n", in_race.load() ? "one-player race" : "frame limit", frame);
        fflush(stdout);
        return false;
    }
    // Frame-based input is repeatable across display rates and cold shader compilation.
    // One Start at frame150, then A every45 game frames; each press lasts5 game frames.
    if (frame >= 150) {
        const unsigned pulse = frame - 150;
        if (pulse % 45 < 5) *buttons |= pulse / 45 == 0 ? 0x1000 : 0x8000;
    }
    return true;
}
// Process-only QA controls. No saved settings or ordinary launch path consumes
// these; they are accepted only with the bounded native-menu autostart enabled.
extern "C" void recomp_mk64_diag_option(uint8_t* rdram, recomp_context* ctx) {
    static const auto options = [] {
        std::array<int, 4> values{-1, -1, -1, -1};
        const char* autostart = std::getenv("MK64_DIAG_AUTOSTART");
        if (!autostart || std::atoi(autostart) <= 0) return values;
        values[3] = std::clamp(std::atoi(autostart), 1, 120) * 30;
        const char* names[] = {"MK64_DIAG_CHARACTER", "MK64_DIAG_COURSE", "MK64_DIAG_STAR_AT"};
        const int maxima[] = {7, 19, 60};
        for (int i = 0; i < 3; ++i) {
            const char* raw = std::getenv(names[i]);
            if (!raw || !*raw) continue;
            char* end = nullptr;
            const long value = std::strtol(raw, &end, 10);
            if (*end == '\0' && value >= 0 && value <= maxima[i]) values[i] = int(value);
        }
        return values;
    }();
    const int index = _arg<0, int>(rdram, ctx);
    _return(ctx, index >= 0 && index < int(options.size()) ? options[index] : -1);
}
extern "C" void recomp_mk64_frame_enabled(uint8_t*, recomp_context* ctx) {
    #ifdef MK64_VR
    _return(ctx, 1);
#else
    _return(ctx, diagnostic_interval() != 0 || std::getenv("MK64_DIAG_AUTOSTART") != nullptr);
#endif
}
extern "C" void recomp_mk64_frame(uint8_t* rdram, recomp_context* ctx) {
    Mk64Frame state;
    std::memcpy(&state, _arg<0, const Mk64Frame*>(rdram, ctx), sizeof(state));
#ifdef MK64_VR
    { std::lock_guard<std::mutex> lock(interaction_mutex); racer=state; }
    dk64vr_game_state vr{};
    vr.frame = state.frame;
    vr.scene = mk64_vr_scene(state);
    std::memcpy(vr.cam_eye, state.eye, sizeof(vr.cam_eye));
    std::memcpy(vr.cam_at, state.at, sizeof(vr.cam_at));
    std::memcpy(vr.cam_up, state.up, sizeof(vr.cam_up));
    std::memcpy(vr.player_pos, state.player_pos[0], sizeof(vr.player_pos));
    vr.sky_dome = dk64vr_is_active() && vr.scene == DK64VR_SCENE_GAMEPLAY;
    vr.fov_y_deg = state.fov; vr.near_z = state.near_z; vr.far_z = state.far_z;
    dk64vr_publish_game_state(&vr);
    while (dk64vr_is_paused() && !exited.load())
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
#endif
    game_frame.store(state.frame);
    in_race.store(state.game_state == 4 && state.screen_mode == 0 && !state.demo);
    const int interval = diagnostic_interval();
    if (interval && state.frame % unsigned(interval) == 0) {
        // Hash simulation fields only; camera and host timing are presentation-dependent.
        unsigned digest = 2166136261u;
        const auto* words = reinterpret_cast<const unsigned char*>(&state.player_pos);
        for (unsigned i = 0; i < sizeof(state.player_pos) + sizeof(state.player_speed) + sizeof(state.player_lap) + sizeof(state.player_rank); ++i)
            digest = (digest ^ words[i]) * 16777619u;
        const double time = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
        printf("[mk64-parity] frame=%u vi=%llu time=%.6f game=%d screen=%d demo=%d pause=%d course=%d timer=%d race=%.6f state=%08x audio=%llu rumble=%llu p0=%.3f,%.3f,%.3f speed=%.3f lap=%d rank=%d\n",
            state.frame, vi_count.load(), time, state.game_state, state.screen_mode, state.demo, state.paused, state.course,
            state.global_timer, state.race_time, digest, audio_samples.load(), rumble_calls.load(),
            state.player_pos[0][0], state.player_pos[0][1], state.player_pos[0][2], state.player_speed[0], state.player_lap[0], state.player_rank[0]);
        fflush(stdout);
    }
}
