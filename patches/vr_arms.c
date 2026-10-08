#include "patches.h"
#include "main.h"
#include "animation.h"
#include "memory.h"
#include "../include/mk64_first_person.h"
#include "../include/mk64_arm_rig.h"
extern Mk64VRInteraction mk64_vr_interaction;
extern int recomp_vr_is_active(void);
extern Vec3s sOriginalPosAnimation;
extern s16 isNotTheFirst, sMatrixStackSize;
int mk64_vr_local_draw;
static Mtx identity;
static void init_identity(void) {
    static int ready;
    if(!ready) { static Mat4 m={{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,1}}; convert_to_fixed_point_matrix_animation(&identity,m); ready=1; }
}
static const u32 package[8]={0x5C6E10,0x5CC610,0x5D2610,0x5DA210,0x5E0610,0x5E7E10,0x5EE610,0x5F5610};
static void matrix_tag(u32 id);
static int first_person_draw(void) {
    return mk64_vr_local_draw && recomp_vr_is_active() && mk64_vr_interaction.enabled;
}
void mk64_vr_begin_kart(void) {
    if(first_person_draw()) matrix_tag(MK64_KART_GROUP);
}
void mk64_vr_end_kart(void) {
    if(first_person_draw()) gEXPopMatrixGroup(gDisplayListHead++,G_MTX_MODELVIEW);
}
static int mk64_vr_selector(Gfx* model) {
    if(!first_person_draw()) return -1;
    u32 pointer=(u32)model & 0xFFFFFF;
    u32 base=package[gPlayers[0].characterId];
    if(pointer<base || pointer>base+6*16 || ((pointer-base)&15)) return -1;
    return (pointer-base)/16;
}
static void matrix_tag(u32 id) {
    gEXMatrixGroupDecomposed(gDisplayListHead++,id,G_EX_PUSH,G_MTX_MODELVIEW,
        G_EX_COMPONENT_SKIP,G_EX_COMPONENT_SKIP,G_EX_COMPONENT_SKIP,
        G_EX_COMPONENT_SKIP,G_EX_COMPONENT_SKIP,G_EX_COMPONENT_SKIP,
        G_EX_COMPONENT_SKIP,G_EX_ORDER_AUTO,G_EX_EDIT_ALLOW,G_EX_COMPONENT_SKIP,G_EX_COMPONENT_SKIP);
}
static void* vr_list_pointer(u32 address) {
    return address>=0x80000000u ? (void*)address : segmented_to_virtual((void*)address);
}
static void mk64_vr_arm_list(Gfx* list,int limb,int depth,unsigned* budget) {
    // Input lists are importer-validated. Bound the live walk even for a bad mod.
    if(depth>16) return;
    while(++*budget<4096) {
        Gfx command=*list++; u32 op=command.words.w0>>24;
        if(op==0xB8) return;
        if(op==0x06) {
            mk64_vr_arm_list(vr_list_pointer(command.words.w1),limb,depth+1,budget);
            if(command.words.w0 & 0x10000) return;
        } else if(op==0x04) {
            if(limb<0) continue; // hidden geometry must still execute its material state
            int count=(command.words.w0>>10)&63, first=(command.words.w0>>17)&127;
            Vtx* vertices=vr_list_pointer(command.words.w1);
            int character=gPlayers[0].characterId;
            for(int i=0;i<count;i++) {
                int weight=mk64_arm_weight(character,limb&1,vertices[i].v.ob[2]);
                matrix_tag(MK64_ARM_GROUP | (character<<16) | (limb<<12) | weight);
                gSPMatrix(gDisplayListHead++,VIRTUAL_TO_PHYSICAL(&identity),G_MTX_NOPUSH|G_MTX_MUL|G_MTX_MODELVIEW);
                gSPVertex(gDisplayListHead++,vertices+i,1,first+i);
                gEXPopMatrixGroup(gDisplayListHead++,G_MTX_MODELVIEW);
            }
        } else if(limb>=0 || (op!=0xBF && op!=0xB1 && op!=0xB5 && op!=0xE4 && op!=0xE5)) {
            *gDisplayListHead++=command;
        }
    }
}
RECOMP_PATCH void render_limb_or_add_mtx(Armature* arg0, s16* arg1, AnimationLimbVector arg2, s32 timeCycle) {
    Vec3f pos;
    Vec3s angle;
    Mat4 modelMatrix;
    s32 i;
    s32 some_offset;
    Gfx* model;
    Gfx* virtualModel;
    virtualModel = arg0->model;
    if (isNotTheFirst == 0) {
        if(first_person_draw() && mk64_vr_selector(arg0->model)==0) {
            // Force one vertex transform at the unmodified model base, with no triangle.
            // RT64 observes it before correcting any local kart/arm transforms.
            static Vtx anchor;
            init_identity(); matrix_tag(MK64_KART_ANCHOR);
            gSPMatrix(gDisplayListHead++,VIRTUAL_TO_PHYSICAL(&identity),G_MTX_NOPUSH|G_MTX_MUL|G_MTX_MODELVIEW);
            gSPVertex(gDisplayListHead++,&anchor,1,0);
            gEXPopMatrixGroup(gDisplayListHead++,G_MTX_MODELVIEW);
        }
        for (i = 0; i < 3; i++) {
            pos[i] = sOriginalPosAnimation[i] + arg0->pos[i];
        }
        isNotTheFirst += 1;
    } else {
        for (i = 0; i < 3; i++) {
            pos[i] = arg0->pos[i];
        }
    }
    for (i = 0; i < 3; i++) {
        if (timeCycle < arg2[i].animation_length) {
            some_offset = timeCycle;
        } else {
            some_offset = 0;
        }
        angle[i] = arg1[arg2[i].indexCycle + some_offset];
    }

    mtxf_translate_rotate2(modelMatrix, pos, angle);
    convert_to_fixed_point_matrix_animation(&gGfxPool->mtxHud[gMatrixHudCount], modelMatrix);
    sMatrixStackSize += 1;
    gSPMatrix(gDisplayListHead++, VIRTUAL_TO_PHYSICAL2(&gGfxPool->mtxHud[gMatrixHudCount++]),
              G_MTX_PUSH | G_MTX_MUL | G_MTX_MODELVIEW);
    if (virtualModel != NULL) {
        model = segmented_to_virtual(virtualModel);
        int selector = mk64_vr_selector(virtualModel);
        if (selector >= 2 && selector <= 5) {
            init_identity();
            unsigned budget=0;
            mk64_vr_arm_list(model,selector-2,0,&budget);
        } else if (selector == 0 || selector == 1 || selector == 6) {
            // Body/head lists also establish inherited combiner, texture and geometry
            // state (different for each racer). Suppress only their geometry.
            unsigned budget=0;
            mk64_vr_arm_list(model,-1,0,&budget);
        } else {
            gSPDisplayList(gDisplayListHead++, model);
        }
    }
}

// A small untextured steering rim. Source kart geometry remains in Amped's draw.
// The same display-time wheel centre/radius/angle drives hit-testing and this group.
void mk64_vr_draw_wheel(void) {
    if(!first_person_draw()) return;
    static Vtx rim[32], spokes[12]; static int ready;
    if(!ready) {
        for(int i=0;i<16;i++) {
            const s16 a=i*4096;
            for(int edge=0;edge<2;edge++) {
                Vtx* v=&rim[i*2+edge]; float r=edge?88:100;
                v->v.ob[0]=(s16)(coss(a)*r); v->v.ob[1]=(s16)(sins(a)*r); v->v.ob[2]=0;
                v->v.flag=0; v->v.tc[0]=v->v.tc[1]=0;
                v->v.cn[0]=v->v.cn[1]=v->v.cn[2]=edge?55:95; v->v.cn[3]=255;
            }
        }
        for(int spoke=0;spoke<3;spoke++) {
            const s16 a=16384+spoke*21845;
            for(int corner=0;corner<4;corner++) {
                Vtx* v=&spokes[spoke*4+corner];
                float distance=corner<2?8:90, width=(corner&1)?5:-5;
                v->v.ob[0]=(s16)(coss(a)*distance-sins(a)*width);
                v->v.ob[1]=(s16)(sins(a)*distance+coss(a)*width); v->v.ob[2]=1;
                v->v.flag=0;v->v.tc[0]=v->v.tc[1]=0;
                v->v.cn[0]=v->v.cn[1]=v->v.cn[2]=120;v->v.cn[3]=255;
            }
        }
        ready=1;
    }
    init_identity(); matrix_tag(MK64_WHEEL_GROUP);
    gEXPushGeometryMode(gDisplayListHead++);
    gEXPushOtherMode(gDisplayListHead++);
    gEXPushCombineMode(gDisplayListHead++);
    gSPMatrix(gDisplayListHead++,VIRTUAL_TO_PHYSICAL(&identity),G_MTX_PUSH|G_MTX_LOAD|G_MTX_MODELVIEW);
    gDPPipeSync(gDisplayListHead++);
    gSPClearGeometryMode(gDisplayListHead++,G_LIGHTING|G_CULL_BACK|G_CULL_FRONT);
    gSPSetGeometryMode(gDisplayListHead++,G_ZBUFFER|G_SHADE|G_SHADING_SMOOTH);
    gDPSetCombineMode(gDisplayListHead++,G_CC_SHADE,G_CC_SHADE);
    gDPSetRenderMode(gDisplayListHead++,G_RM_AA_ZB_OPA_SURF,G_RM_AA_ZB_OPA_SURF2);
    gSPVertex(gDisplayListHead++,rim,32,0);
    for(int i=0;i<16;i++) {
        int j=(i+1)&15;
        gSP2Triangles(gDisplayListHead++,i*2,i*2+1,j*2,0,i*2+1,j*2+1,j*2,0);
    }
    gSPVertex(gDisplayListHead++,spokes,12,0);
    for(int spoke=0;spoke<3;spoke++) {
        int v=spoke*4;
        gSP2Triangles(gDisplayListHead++,v,v+1,v+2,0,v+1,v+3,v+2,0);
    }
    gSPPopMatrix(gDisplayListHead++,G_MTX_MODELVIEW);
    gEXPopCombineMode(gDisplayListHead++);
    gEXPopOtherMode(gDisplayListHead++);
    gEXPopGeometryMode(gDisplayListHead++);
    gEXPopMatrixGroup(gDisplayListHead++,G_MTX_MODELVIEW);
}
