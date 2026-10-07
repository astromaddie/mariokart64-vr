// The host's requests to the game (dk64vr_control.h), outside the frozen game-state contract:
// the standby/menu pause flag (the game thread waits on it in recomp_vr_publish_game_state,
// src/game/vr_api.cpp), comfort-turn degrees for a camera patch to take, and the HUD diagnostic.
#include <atomic>
#include <chrono>
#include <cstdio>
#include <mutex>

#include "../include/dk64vr_control.h"
#include "../bridge/dk64vr_turn.h"

namespace {
std::atomic<int> g_paused{0};
std::mutex g_turn_mutex;
dk64vr::TurnRequests g_turn_requests;
std::atomic<int> g_turn_applicable{0};
std::atomic<int> g_hud_diag{0};
}

extern "C" void dk64vr_set_paused(int paused) {
    g_paused.store(paused != 0 ? 1 : 0, std::memory_order_relaxed);
    if (paused) dk64vr_clear_turn();
}

extern "C" int dk64vr_is_paused(void) {
    return g_paused.load(std::memory_order_relaxed);
}

extern "C" void dk64vr_request_turn(int degrees) {
    std::lock_guard<std::mutex> lock(g_turn_mutex);
    g_turn_requests.add(degrees, std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

extern "C" int dk64vr_take_turn(void) {
    std::lock_guard<std::mutex> lock(g_turn_mutex);
    return g_turn_requests.take(true, std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

extern "C" int dk64vr_take_turn_if_applicable(int applicable) {
    std::lock_guard<std::mutex> lock(g_turn_mutex);
    const int previous = g_turn_applicable.exchange(applicable != 0);
    if (previous != (applicable != 0))
        std::printf("[vr-turn] camera %s\n", applicable ? "applicable" : "not applicable");
    return g_turn_requests.take(applicable != 0, std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

extern "C" int dk64vr_turn_applicable(void) { return g_turn_applicable.load(); }
extern "C" void dk64vr_clear_turn(void) {
    std::lock_guard<std::mutex> lock(g_turn_mutex);
    g_turn_applicable.store(0);
    g_turn_requests.degrees = 0;
}

extern "C" void dk64vr_request_hud_diag(void) {
    g_hud_diag.store(1);
}

extern "C" int dk64vr_take_hud_diag(void) {
    return g_hud_diag.exchange(0);
}
