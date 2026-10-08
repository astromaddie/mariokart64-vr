#include "patches.h"
#include "vr_render.h"
#include "animation.h"
#include "bomb_kart.h"
extern Vec3f D_80183E40;
extern s32 D_8018D400;

extern u8 D_800E471C[];
extern void func_800562E4(s32, s32, s32);

extern void func_8008A454(s32 objectIndex, s32 cameraId, s32 distance);

// All of these leaves draw camera-facing cards, not their adjacent shadows.
// RT64 faces them after interpolation using one head-centre point for both eyes.
// Flat/cinema rendering ignores the profile and retains the original transforms.
static u32 sprite_owner, sprite_slot;
static void sprite_begin(const void* position) {
    // The few callers using shared scratch/stack positions supply their stable
    // object identity. A per-owner slot distinguishes wheels and effect cards.
    u32 tag = sprite_owner ? sprite_owner + ++sprite_slot : TAG_WORLD_SPRITE(position);
    gEXMatrixGroupDecomposedNormal(gDisplayListHead++, tag,
        G_EX_PUSH, G_MTX_MODELVIEW, G_EX_EDIT_ALLOW);
}
static void sprite_end(void) {
    gEXPopMatrixGroup(gDisplayListHead++, G_MTX_MODELVIEW);
}

RECOMP_PATCH void func_800431B0(Vec3f pos, Vec3su orientation, f32 scale, Vtx* vtx) {
    sprite_begin(pos);
    rsp_set_matrix_transformation(pos, orientation, scale);
    gSPVertex(gDisplayListHead++, vtx, 4, 0);
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D006940 /* common_rectangle_display */);
    sprite_end();
}

RECOMP_PATCH void draw_2d_texture_at(Vec3f arg0, Vec3su arg1, f32 arg2, u8* tlut, u8* texture, Vtx* arg5, s32 arg6, s32 arg7,
                        s32 arg8, s32 arg9) {
    sprite_begin(arg0);
    rsp_set_matrix_transformation(arg0, arg1, arg2);
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D007D78);
    draw_rectangle_texture_overlap(tlut, texture, arg5, arg6, arg7, arg8, arg9);
    sprite_end();
}

RECOMP_PATCH void func_80048130(Vec3f arg0, Vec3su arg1, f32 arg2, u8* tlut, u8* texture, Vtx* arg5, s32 arg6, s32 arg7, s32 arg8,
                   s32 arg9, s32 argA) {
    sprite_begin(arg0);
    rsp_set_matrix_transformation(arg0, arg1, arg2);
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D007D78);
    func_8004747C(tlut, texture, arg5, arg6, arg7, arg8, arg9, argA);
    sprite_end();
}

RECOMP_PATCH void func_800484BC(Vec3f arg0, Vec3su arg1, f32 arg2, s32 arg3, u8* tlut, u8* texture, Vtx* arg6, s32 arg7, s32 arg8,
                   s32 arg9, s32 argA) {
    sprite_begin(arg0);
    rsp_set_matrix_transformation(arg0, arg1, arg2);
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D007E18);
    set_transparency(arg3);
    draw_rectangle_texture_overlap(tlut, texture, arg6, arg7, arg8, arg9, argA);
    sprite_end();
}

RECOMP_PATCH void func_800485C4(Vec3f arg0, Vec3su arg1, f32 arg2, s32 arg3, u8* tlut, u8* texture, Vtx* arg6, s32 arg7, s32 arg8,
                   s32 arg9, s32 argA) {
    sprite_begin(arg0);
    rsp_set_matrix_transformation(arg0, arg1, arg2);
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D007E98);
    gDPSetAlphaCompare(gDisplayListHead++, G_AC_DITHER);
    gDPSetRenderMode(gDisplayListHead++, G_RM_AA_ZB_XLU_SURF, G_RM_AA_ZB_XLU_SURF2);

    set_transparency(arg3);
    draw_rectangle_texture_overlap(tlut, texture, arg6, arg7, arg8, arg9, argA);

    gDPSetAlphaCompare(gDisplayListHead++, G_AC_NONE);
    sprite_end();
}

RECOMP_PATCH void func_800468E0(Vec3f arg0, Vec3su arg1, f32 arg2, u8* texture, Vtx* arg4, s32 arg5, s32 arg6, UNUSED s32 arg7,
                   s32 arg8, s32 arg9) {
    sprite_begin(arg0);
    rsp_set_matrix_transformation(arg0, arg1, arg2);
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D0079C8);
    func_80045F18(texture, arg4, arg5, arg6, arg8, arg9);
    sprite_end();
}

RECOMP_PATCH void func_8029794C(Vec3f pos, Vec3s rot, f32 scale) {
    Mat4 sp20;
    gEXMatrixGroupDecomposedNormal(gDisplayListHead++, TAG_OBJECT(pos), G_EX_PUSH, G_MTX_MODELVIEW, G_EX_EDIT_ALLOW);
    pos[1] += 2.0f;

    mtxf_pos_rotation_xyz(sp20, pos, rot);
    mtxf_scale(sp20, scale);
    if (render_set_position(sp20, 0) != 0) {
        gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D007B20);
        pos[1] -= 2.0f;
    }
    sprite_end();
}

// DK Jungle has billboard tree variants and a genuinely 3D palm (variant 6).
RECOMP_PATCH void render_palm_trees(Camera* camera, Mat4 arg1, UNUSED struct Actor* actor) {
    s32 segment = SEGMENT_NUMBER2(0x06013F78);
    s32 offset = SEGMENT_OFFSET(0x06013F78);
    struct UnkActorSpawnData* var_s1 =
        (struct UnkActorSpawnData*) VIRTUAL_TO_PHYSICAL2(gSegmentTable[segment] + offset);
    UNUSED s32 pad;
    Vec3f spD4;
    f32 var_f22;
    Mat4 sp90;
    Vec3s sp88 = { 0, 0, 0 };
    s32 test;

    if (gGamestate == CREDITS_SEQUENCE) {
        var_f22 = 9000000.0f;
    } else {
        var_f22 = 1000000.0f;
    }

    gSPTexture(gDisplayListHead++, 0xFFFF, 0xFFFF, 0, G_TX_RENDERTILE, G_ON);
    gDPSetCombineMode(gDisplayListHead++, G_CC_MODULATEIDECALA, G_CC_MODULATEIDECALA);
    gDPSetRenderMode(gDisplayListHead++, G_RM_AA_ZB_TEX_EDGE, G_RM_AA_ZB_TEX_EDGE2);

    while (var_s1->pos[0] != END_OF_SPAWN_DATA) {
        test = var_s1->someId;
        if (test & 0x0800) {
            var_s1++;
            continue;
        }

        if ((test & 0x0400) && ((gIsGamePaused == 0) || (camera == camera1))) {
            var_s1->pos[1] += 0xA;
            if (var_s1->pos[1] >= 0x321) {
                var_s1->someId |= 0x0800;
            }
        }
        spD4[0] = var_s1->pos[0] * gCourseDirection;
        spD4[1] = var_s1->pos[1];
        spD4[2] = var_s1->pos[2];

        if (is_within_render_distance(camera->pos, spD4, camera->rot[1], 0.0f, gCameraZoom[camera - camera1], var_f22) <
            0.0f) {
            var_s1++;
            continue;
        }

        test &= 0xF;
        test = (s16) test;
        if (test == 6) {
            mtxf_pos_rotation_xyz(sp90, spD4, sp88);
            if (!(gMatrixObjectCount < MTX_OBJECT_POOL_SIZE)) {
                break;
            }
            render_set_position(sp90, 0);
            goto dummylabel;
        } else {
            arg1[3][0] = spD4[0];
            arg1[3][1] = spD4[1];
            arg1[3][2] = spD4[2];
            if (gMatrixObjectCount < MTX_OBJECT_POOL_SIZE) {
                gEXMatrixGroupDecomposedNormal(gDisplayListHead++, TAG_WORLD_ACTOR(var_s1),
                    G_EX_PUSH, G_MTX_MODELVIEW, G_EX_EDIT_ALLOW);
                render_set_position(arg1, 0);
            dummylabel:
                gSPClearGeometryMode(gDisplayListHead++, G_LIGHTING);
                switch (test) {
                    case 0:
                        gSPDisplayList(gDisplayListHead++, (Gfx*) 0x06010CC0);
                        break;
                    case 4:
                        gSPDisplayList(gDisplayListHead++, (Gfx*) 0x06011DC8);
                        break;
                    case 5:
                        gSPDisplayList(gDisplayListHead++, (Gfx*) 0x06012EF0);
                        break;
                    case 6:
                        gSPDisplayList(gDisplayListHead++, (Gfx*) 0x060138D0);
                        break;
                }
                if (test != 6) sprite_end();
            } else {
                break;
            }
            var_s1++;
        }
    }
}

// Only the balloon's flat alternate; its near 3D model and shadow stay put.
RECOMP_PATCH void func_80055CCC(s32 objectIndex, s32 cameraId) {
    UNUSED s32 pad;
    f32 test;
    Camera* camera;

    camera = &camera1[cameraId];
    if (gObjectList[objectIndex].state >= 2) {
        func_8008A454(objectIndex, cameraId, 0x0000012C);
        test = gObjectList[objectIndex].pos[1] - gObjectList[objectIndex].surfaceHeight;
        func_8004A6EC(objectIndex, (20.0 / test) + 0.5);
        if (is_obj_index_flag_status_inactive(objectIndex, 0x00100000) != 0) {
            func_80043328(gObjectList[objectIndex].pos, (u16*) gObjectList[objectIndex].direction_angle,
                          gObjectList[objectIndex].sizeScaling, (Gfx*) 0x0600F960);
            gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0600F650);
        } else {
            D_80183E80[0] = (s16) gObjectList[objectIndex].direction_angle[0];
            D_80183E80[1] =
                (s16) (func_800418AC(gObjectList[objectIndex].pos[0], gObjectList[objectIndex].pos[2], camera->pos) +
                       0x8000);
            D_80183E80[2] = (u16) gObjectList[objectIndex].direction_angle[2];
            sprite_begin(gObjectList[objectIndex].pos);
            func_80043328(gObjectList[objectIndex].pos, D_80183E80, gObjectList[objectIndex].sizeScaling,
                          (Gfx*) 0x0600FBE0);
            gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0600FA20);
            sprite_end();
            if (gPlayerCountSelection1 == 1) {
                gObjectList[objectIndex].direction_angle[1] = 0;
            }
        }
    }
}

// Stable identities for the native scratch-position sprite callers.
RECOMP_PATCH void func_80055AB8(s32 objectIndex, s32 cameraId) {
    sprite_owner = 0x62000000u | ((u32)objectIndex << 8);
    sprite_slot = 0;
    Camera* camera;

    camera = &camera1[cameraId];
    if (gObjectList[objectIndex].state >= 2) {
        if (is_obj_flag_status_active(objectIndex, 0x00100000) != 0) {
            D_80183E40[0] = gObjectList[objectIndex].pos[0];
            D_80183E40[1] = gObjectList[objectIndex].pos[1] + 16.0;
            D_80183E40[2] = gObjectList[objectIndex].pos[2];
            D_80183E80[0] = 0;
            D_80183E80[1] =
                func_800418AC(gObjectList[objectIndex].pos[0], gObjectList[objectIndex].pos[2], camera->pos);
            D_80183E80[2] = 0x8000;
            func_800468E0(D_80183E40, D_80183E80, 0.54f, (u8*) 0x06012028, (Vtx*) 0x0D0062B0, 0x00000020,
                          0x00000040, 0x00000020, 0x00000040, 5);
        } else {
            rsp_set_matrix_transformation(gObjectList[objectIndex].pos, gObjectList[objectIndex].direction_angle,
                                          gObjectList[objectIndex].sizeScaling);
            gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D0077D0);
            render_animated_model((Armature*) gObjectList[objectIndex].model,
                                  (Animation**) gObjectList[objectIndex].vertex, 0,
                                  (s16) gObjectList[objectIndex].textureListIndex);
        }
    }
    sprite_owner = 0;
}

// Stable identities for the native scratch-position sprite callers.
RECOMP_PATCH void func_800563DC(s32 objectIndex, s32 cameraId, s32 arg2) {
    sprite_owner = 0x62000000u | ((u32)objectIndex << 8);
    sprite_slot = 0;
    s32 temp_s0;
    s32 temp_v0;
    s32 residue;
    Camera* camera;
    Object* object;

    camera = &camera1[cameraId];
    object = &gObjectList[objectIndex];
    residue = D_801655CC % 4U;
    D_80183E40[0] = object->pos[0];
    D_80183E40[1] = object->pos[1] + 1.0;
    D_80183E40[2] = object->pos[2];
    D_80183E80[0] = 0;
    D_80183E80[1] = func_800418AC(object->pos[0], object->pos[2], camera->pos);
    D_80183E80[2] = 0x8000;
    sprite_begin(0);
    rsp_set_matrix_transformation(D_80183E40, D_80183E80, 0.2f);
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D007E98);
    func_8004B310(arg2);
    draw_rectangle_texture_overlap((u8*) 0x0D02A858, ((u8*) 0x0D029858 + residue * 1024), (Vtx*) 0x0D005AE0, 0x00000020,
                                   0x00000020, 0x00000020, 0x00000020);
    temp_s0 = D_8018D400;
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D007B00);
    func_8004B414(0, 0, 0, arg2);
    D_80183E40[1] = D_80183E40[1] + 4.0;
    D_80183E80[2] = 0;
    func_800562E4(temp_s0 % 3, temp_s0 % 4, arg2);
    temp_v0 = temp_s0 + 1;
    D_80183E80[2] = 0x6000;
    func_800562E4(temp_v0 % 3, temp_v0 % 4, arg2);
    temp_v0 = temp_s0 + 2;
    D_80183E80[2] = 0xA000;
    func_800562E4(temp_v0 % 3, temp_v0 % 4, arg2);
    gSPTexture(gDisplayListHead++, 1, 1, 0, G_TX_RENDERTILE, G_OFF);
    sprite_end();
    sprite_owner = 0;
}

// Stable identities for the native scratch-position sprite callers.
RECOMP_PATCH void func_8005669C(s32 objectIndex, UNUSED s32 arg1, s32 arg2) {
    sprite_owner = 0x62000000u | ((u32)objectIndex << 8);
    sprite_slot = 16;
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D0079E8);
    func_8004B310(arg2);
    load_texture_block_rgba16_mirror((u8*) 0x0D02AA58, 0x00000010, 0x00000010);
    D_80183E40[1] = gObjectList[objectIndex].pos[1] - 2.0;
    D_80183E40[0] = gObjectList[objectIndex].pos[0] + 2.0;
    D_80183E40[2] = gObjectList[objectIndex].pos[2] + 2.0;
    func_800431B0(D_80183E40, D_80183E80, 0.15f, (Vtx*) 0x0D005770);
    D_80183E40[0] = gObjectList[objectIndex].pos[0] + 2.0;
    D_80183E40[2] = gObjectList[objectIndex].pos[2] - 2.0;
    func_800431B0(D_80183E40, D_80183E80, 0.15f, (Vtx*) 0x0D005770);
    D_80183E40[0] = gObjectList[objectIndex].pos[0] - 2.0;
    D_80183E40[2] = gObjectList[objectIndex].pos[2] - 2.0;
    func_800431B0(D_80183E40, D_80183E80, 0.15f, (Vtx*) 0x0D005770);
    D_80183E40[0] = gObjectList[objectIndex].pos[0] - 2.0;
    D_80183E40[2] = gObjectList[objectIndex].pos[2] + 2.0;
    func_800431B0(D_80183E40, D_80183E80, 0.15f, (Vtx*) 0x0D005770);
    gSPTexture(gDisplayListHead++, 1, 1, 0, G_TX_RENDERTILE, G_OFF);
    sprite_owner = 0;
}

// Stable identities for the native scratch-position sprite callers.
RECOMP_PATCH void func_80056BF0(s32 bombIndex) {
    sprite_owner = 0x62100000u | ((u32)bombIndex << 8);
    sprite_slot = 0;
    UNUSED s32 stackPadding;
    u8 thing;
    s32 temp_s0;
    s32 temp_v0;
    u8* bombFrame;
    BombKart* sp40 = &gBombKarts[bombIndex];

    temp_v0 = D_801655CC % 6U;
    thing = D_800E471C[temp_v0];
    bombFrame = ((u8*) 0x0D029858 + thing * 1024);
    D_80183E40[0] = sp40->bombPos[0];
    D_80183E40[1] = sp40->bombPos[1] + 1.0;
    D_80183E40[2] = sp40->bombPos[2];
    sprite_begin(0);
    draw_2d_texture_at(D_80183E40, D_80183E80, 0.25f, (u8*) 0x0D02A858, bombFrame, (Vtx*) 0x0D005AE0, 0x20, 0x20, 0x20,
                       0x20);
    temp_s0 = D_8018D400;
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D007B00);
    func_8004B414(0, 0, 0, 0xFF);
    D_80183E40[1] = sp40->bombPos[1] + 5.0;
    D_80183E80[2] = 0;
    func_800562E4((s32) temp_s0 % 3, temp_s0 % 4, 0xFFU);
    temp_v0 = temp_s0 + 1;
    D_80183E80[2] = 0x6000;
    func_800562E4(temp_v0 % 3, temp_v0 % 4, 0xFFU);
    temp_v0 = temp_s0 + 2;
    D_80183E80[2] = 0xA000;
    func_800562E4(temp_v0 % 3, temp_v0 % 4, 0xFFU);
    sprite_end();
    sprite_owner = 0;
}

// Stable identities for the native scratch-position sprite callers.
RECOMP_PATCH void func_80056E24(s32 bombIndex, Vec3f arg1) {
    sprite_owner = 0x62100000u | ((u32)bombIndex << 8);
    sprite_slot = 0;
    UNUSED s32 stackPadding[2];
    BombKart* sp2C = &gBombKarts[bombIndex];

    D_80183E80[0] = 0;
    D_80183E80[2] = 0x8000;
    gSPDisplayList(gDisplayListHead++, (Gfx*) 0x0D0079C8);
    load_texture_block_rgba16_mirror((u8*) 0x0D02AA58, 0x00000010, 0x00000010);
    D_80183E80[1] = func_800418AC(sp2C->wheel1Pos[0], sp2C->wheel1Pos[2], arg1);
    func_800431B0(sp2C->wheel1Pos, D_80183E80, 0.15f, (Vtx*) 0x0D005770);
    D_80183E80[1] = func_800418AC(sp2C->wheel2Pos[0], sp2C->wheel2Pos[2], arg1);
    func_800431B0(sp2C->wheel2Pos, D_80183E80, 0.15f, (Vtx*) 0x0D005770);
    D_80183E80[1] = func_800418AC(sp2C->wheel3Pos[0], sp2C->wheel3Pos[2], arg1);
    func_800431B0(sp2C->wheel3Pos, D_80183E80, 0.15f, (Vtx*) 0x0D005770);
    D_80183E80[1] = func_800418AC(sp2C->wheel4Pos[0], sp2C->wheel4Pos[2], arg1);
    func_800431B0(sp2C->wheel4Pos, D_80183E80, 0.15f, (Vtx*) 0x0D005770);
    gSPTexture(gDisplayListHead++, 1, 1, 0, G_TX_RENDERTILE, G_OFF);
    sprite_owner = 0;
}
