#include "patches.h"
#include "racing/collision.h"
#include "vr_render.h"
RECOMP_PATCH void render_course_segments(uintptr_t addr, struct UnkStruct_800DC5EC* arg1) {
    Player* player = arg1->player;
    Camera* camera = arg1->camera;
    u32 segment = SEGMENT_NUMBER2(addr);
    u32 offset = SEGMENT_OFFSET(addr);
    //! @todo Should be Gfx*
    s32* gfx = (s32*) VIRTUAL_TO_PHYSICAL2(gSegmentTable[segment] + offset);
    s16 direction;
    s16 index;
    s16 sp1E;
    s16 temp_v0_3;
    u16 rot;
    if (gIsMirrorMode) {
        rot = (u16) (camera->rot[1] + (mk64_vr_world() ? recomp_mk64_vr_yaw() : 0));
        if (rot < 0x2000) {
            direction = SOUTH;
        } else if (rot < 0x6000) {
            direction = WEST;
        } else if (rot < 0xA000) {
            direction = NORTH;
        } else if (rot < 0xE000) {
            direction = EAST;
        } else {
            direction = SOUTH;
        }
    } else {
        rot = (u16) (camera->rot[1] + (mk64_vr_world() ? recomp_mk64_vr_yaw() : 0));
        if (rot < 0x2000) {
            direction = SOUTH;
        } else if (rot < 0x6000) {
            direction = EAST;
        } else if (rot < 0xA000) {
            direction = NORTH;
        } else if (rot < 0xE000) {
            direction = WEST;
        } else {
            direction = SOUTH;
        }
    }
    arg1->playerDirection = direction;

    if (D_80152300[camera - camera1] == 1) {
        sp1E = get_track_section_id(camera->collision.meshIndexZX);
        temp_v0_3 = get_track_section_id(player->collision.meshIndexZX);
        index = sp1E - temp_v0_3;
        if ((index < 2) && (index >= -1)) {
            if (sp1E == 255) {
                if (temp_v0_3 == 255) {
                    index = arg1->pathCounter;
                } else if (player->collision.surfaceDistance[2] > 30.0f) {
                    index = arg1->pathCounter;
                } else {
                    index = temp_v0_3;
                }
            } else if (camera->collision.surfaceDistance[2] > 30.0f) {
                index = arg1->pathCounter;
            } else {
                index = sp1E;
            }
        } else {

            switch (gCurrentCourseId) {
                case COURSE_BOWSER_CASTLE:
                    if ((temp_v0_3 >= 0x11) && (temp_v0_3 < 0x18)) {
                        index = temp_v0_3;
                    } else if ((temp_v0_3 == 255) && (sp1E != 255)) {
                        index = sp1E;
                    } else if ((temp_v0_3 != 255) && (sp1E == 255)) {
                        index = temp_v0_3;
                    } else {
                        index = arg1->pathCounter;
                    }
                    break;
                case COURSE_CHOCO_MOUNTAIN:
                    if ((temp_v0_3 >= 0xE) && (temp_v0_3 < 0x16)) {
                        index = temp_v0_3;
                    } else if ((temp_v0_3 == 255) && (sp1E != 255)) {
                        index = sp1E;
                    } else if ((temp_v0_3 != 255) && (sp1E == 255)) {
                        index = temp_v0_3;
                    } else {
                        index = arg1->pathCounter;
                    }
                    break;
                default:
                    if (temp_v0_3 == 255) {
                        index = arg1->pathCounter;
                    } else if (player->collision.surfaceDistance[2] > 30.0f) {
                        index = arg1->pathCounter;
                    } else {
                        index = temp_v0_3;
                    }
                    break;
            }
        }
    } else {
        index = get_track_section_id(camera->collision.meshIndexZX);
        if (camera->collision.surfaceDistance[2] > 30.0f) {
            index = arg1->pathCounter;
        } else if (index == 255) {
            index = arg1->pathCounter;
        }
    }

    arg1->pathCounter = index;
    index = ((index - 1) * 4) + direction;
    gSPDisplayList(gDisplayListHead++, gfx[index]);
}
