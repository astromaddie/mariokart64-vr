// Requests from the VR host to the game side (src/game/vr_api.cpp), outside the frozen
// game-state contract.
//
// Pause: freezing the game while the headset is off or another app has focus (standard.md section 0:
// on focus loss, pause the game and its audio; SKILL.md: standby freezes the simulation and
// keeps polling). The VR host sets the flag; the game thread waits inside the once-per-frame
// game-state publish (src/game/vr_api.cpp), after the frame's display lists are submitted, so
// no game thread runs and no lock is held while it waits. The VI, gfx, audio and RT64 threads
// keep running; the audio queue drains to silence. Always 0 without the VR renderer.
#ifndef DK64VR_CONTROL_H
#define DK64VR_CONTROL_H

#ifdef __cplusplus
extern "C" {
#endif

void dk64vr_set_paused(int paused);
int dk64vr_is_paused(void);

// Comfort turn: the host adds whole degrees (positive = right); the camera patch
// (Banjo: patches/vr_turn.c, before ncCamera_update dispatch) takes them through
// recomp_vr_take_turn once per camera update and turns the game camera's heading. A request
// older than 0.3 s is dropped, so a turn asked for where the camera does not run (a cutscene,
// first person) never lands later.
void dk64vr_request_turn(int degrees);
int dk64vr_take_turn(void);
// Banjo polls with current applicability, even for disabled/scripted cameras. Rejection
// drains the queue; the host suppresses new input and compensation until a free camera reports.
int dk64vr_take_turn_if_applicable(int applicable);
int dk64vr_turn_applicable(void);
void dk64vr_clear_turn(void);

// Diagnostic (diag_hud_seconds): ask the game to show its HUD counters once, through its own
// "show this counter" function, so an unattended run can dump the HUD. Taken by vr_frame_hook.
void dk64vr_request_hud_diag(void);
int dk64vr_take_hud_diag(void);

// Diagnostic (diag_save_in_play): the host sets this once from the setting; the game side reads it
// through recomp_vr_diag_save_in_play (src/game/vr_api.cpp) and saves the game once in play.
// Always 0 without the VR host.
void dk64vr_set_diag_save_in_play(int enabled);
int dk64vr_diag_save_in_play(void);

#ifdef __cplusplus
}
#endif

#endif
