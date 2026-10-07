// The host tests run the shared VR layer with DK64's profile, the numbers they were written for.
#include "vr_game_profile.h"

static const uint32_t dk64_camera_groups[] = { 5u, 4u };

const vr_game_profile *vr_game_profile_get(void) {
    static const vr_game_profile profile = { dk64_camera_groups, 2, 25.2f, 15.0f, 10.0f, "DK" };
    return &profile;
}
