#ifndef MK64_VR_RENDER_H
#define MK64_VR_RENDER_H
extern int recomp_vr_is_active(void);
extern int recomp_mk64_vr_yaw(void);
static inline int mk64_vr_world(void) {
    return recomp_vr_is_active() && gGamestate == 4 && gActiveScreenMode == 0 &&
        !gDemoMode && !gIsGamePaused && gCourseTimer > 0.0f;
}
// Render-only viewport; never modifies the game's intro/split-screen camera wrapper.
static inline void mk64_vr_full_viewport(void) {
    gEXSetViewportAlign(gDisplayListHead++, G_EX_ORIGIN_NONE, 0, 0);
    gSPViewport(gDisplayListHead++, VIRTUAL_TO_PHYSICAL(&D_802B8880));
    gDPSetScissor(gDisplayListHead++, G_SC_NON_INTERLACE, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT);
}
void mk64_vr_sky(Vtx* colours, Camera* camera);
void mk64_vr_clouds(s32 start);
#endif
