#include "patches.h"
#include "vr_render.h"

// A surrounding sky using the original course colours and cloud/star textures. Storage follows
// the game's two graphics pools. RT64's sky camera group removes eye translation and disparity.
static Mtx sky_projection[2], sky_view[2], sky_identity[2];
static u16 sky_norm[2];
static Vtx sky_vertices[2][16 * 8];
static Vtx cloud_vertices[2][128][4];

void mk64_vr_sky(Vtx* colours, Camera* camera) {
    int slot = gGlobalTimer & 1;
    u16 norm;
    course_set_skybox_colours(colours);
    guPerspective(&sky_projection[slot], &norm, gCameraZoom[0], gScreenAspect, 1.0f, 30000.0f, 1.0f);
    guLookAt(&sky_view[slot], camera->pos[0], camera->pos[1], camera->pos[2], camera->lookAt[0],
        camera->lookAt[1], camera->lookAt[2], camera->up[0], camera->up[1], camera->up[2]);
    guScale(&sky_identity[slot], 1, 1, 1);
    sky_norm[slot] = norm;
    gEXMatrixGroupSimple(gDisplayListHead++, 0xFFFFAAE0, G_EX_NOPUSH, G_MTX_PROJECTION,
        G_EX_COMPONENT_INTERPOLATE, G_EX_COMPONENT_INTERPOLATE, G_EX_COMPONENT_INTERPOLATE,
        G_EX_COMPONENT_INTERPOLATE, G_EX_COMPONENT_INTERPOLATE, G_EX_ORDER_LINEAR,
        G_EX_EDIT_NONE, G_EX_COMPONENT_SKIP, G_EX_COMPONENT_SKIP);
    init_rdp();
    mk64_vr_full_viewport();
    gSPPerspNormalize(gDisplayListHead++, norm);
    gSPMatrix(gDisplayListHead++, VIRTUAL_TO_PHYSICAL(&sky_projection[slot]), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_PROJECTION);
    gSPMatrix(gDisplayListHead++, VIRTUAL_TO_PHYSICAL(&sky_view[slot]), G_MTX_NOPUSH | G_MTX_MUL | G_MTX_PROJECTION);
    gSPMatrix(gDisplayListHead++, VIRTUAL_TO_PHYSICAL(&sky_identity[slot]), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
    gSPClearGeometryMode(gDisplayListHead++, G_ZBUFFER | G_LIGHTING | G_CULL_BACK | G_CULL_FRONT);
    gSPSetGeometryMode(gDisplayListHead++, G_SHADE | G_SHADING_SMOOTH);
    gDPSetCombineMode(gDisplayListHead++, G_CC_SHADE, G_CC_SHADE);
    gDPSetRenderMode(gDisplayListHead++, G_RM_OPA_SURF, G_RM_OPA_SURF2);
    gSPTexture(gDisplayListHead++, 0, 0, 0, G_TX_RENDERTILE, G_OFF);
    for (int side = 0; side < 16; ++side) {
        Vtx* v = &sky_vertices[slot][side * 8];
        for (int half = 0; half < 2; ++half) {
            for (int corner = 0; corner < 4; ++corner) {
                int edge = (corner == 1 || corner == 2);
                int bottom = corner >= 2;
                u16 angle = (side + edge) * 4096;
                int colour = half ? (bottom ? 5 : 4) : (bottom ? 1 : 0);
                Vtx* out = &v[half * 4 + corner];
                *out = colours[colour];
                out->v.ob[0] = camera->pos[0] + sins(angle) * (bottom == half ? 10.0f : 10000.0f);
                out->v.ob[2] = camera->pos[2] + coss(angle) * (bottom == half ? 10.0f : 10000.0f);
                out->v.ob[1] = camera->pos[1] + (half ? (bottom ? -14000 : 0) : (bottom ? 0 : 14000));
                out->v.cn[3] = 255;
            }
        }
        gSPVertex(gDisplayListHead++, v, 8, 0);
        gSP2Triangles(gDisplayListHead++, 0, 1, 2, 0, 0, 2, 3, 0);
        gSP2Triangles(gDisplayListHead++, 4, 5, 6, 0, 4, 6, 7, 0);
    }
}

void mk64_vr_clouds(s32 start) {
    int slot = gGlobalTimer & 1;
    Camera* camera = &cameras[0];
    // func_80057FC4 installed the HUD orthographic projection before this cloud draw.
    // Restore the retained sky camera instead of projecting world cloud vertices through it.
    mk64_vr_full_viewport();
    gSPPerspNormalize(gDisplayListHead++, sky_norm[slot]);
    gSPMatrix(gDisplayListHead++, VIRTUAL_TO_PHYSICAL(&sky_projection[slot]), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_PROJECTION);
    gSPMatrix(gDisplayListHead++, VIRTUAL_TO_PHYSICAL(&sky_view[slot]), G_MTX_NOPUSH | G_MTX_MUL | G_MTX_PROJECTION);
    gSPDisplayList(gDisplayListHead++, (Gfx*)0x0D007A60);
    gSPClearGeometryMode(gDisplayListHead++, G_ZBUFFER | G_LIGHTING | G_CULL_BACK | G_CULL_FRONT);
    gSPMatrix(gDisplayListHead++, VIRTUAL_TO_PHYSICAL(&sky_identity[slot]), G_MTX_NOPUSH | G_MTX_LOAD | G_MTX_MODELVIEW);
    for (int i = 0; i < D_8018D1F0 && i < 128; ++i) {
        Object* object = &gObjectList[D_8018CC80[start + i]];
        if (!object->activeTexture || !object->vertex) continue;
        u16 angle = -object->direction_angle[1];
        float sx = sins(angle), cz = coss(angle);
        // Convert the authored 320x240 screen units to a tangent plane at radius10000.
        u16 half_fov = (u16)(gCameraZoom[0] * (65536.0f / 720.0f));
        float unit = 10000.0f * sins(half_fov) / (120.0f * coss(half_fov));
        Vtx* v = cloud_vertices[slot][i];
        uintptr_t address = (uintptr_t)object->vertex;
        // Vertex display-list pointers may use segment0D; CPU reads require KSEG0.
        Vtx* source = address < 0x10000000u ?
            (Vtx*)((gSegmentTable[address >> 24] + (address & 0xFFFFFFu)) | 0x80000000u) : object->vertex;
        for (int j = 0; j < 4; ++j) {
            v[j] = source[j];
            float x = v[j].v.ob[0] * object->sizeScaling * unit;
            float y = (v[j].v.ob[1] * object->sizeScaling + object->unk_09E) * unit;
            v[j].v.ob[0] = camera->pos[0] + sx * 10000.0f + cz * x;
            v[j].v.ob[1] = camera->pos[1] + y;
            v[j].v.ob[2] = camera->pos[2] + cz * 10000.0f - sx * x;
        }
        func_80044DA0(object->activeTexture, object->textureWidth, object->textureHeight);
        if ((u8)D_8018D230) func_8004B138(255, 255, 255, object->primAlpha);
        else func_8004B6C4(255, 255, 255);
        gSPVertex(gDisplayListHead++, v, 4, 0);
        gSPDisplayList(gDisplayListHead++, (Gfx*)0x0D006940);
    }
}
