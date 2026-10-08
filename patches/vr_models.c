#include "patches.h"
#include "vr_render.h"
#include "../include/mk64_visual_assets.h"
extern int recomp_vr_is_active(void);
extern int mk64_vr_item_is_held(struct Actor* actor);
extern void func_8004B35C(s32, s32, s32, s32);

const Mk64VisualAssets* mk64_vr_visual_assets(void) {
    const Mk64VisualAssets* assets=(const Mk64VisualAssets*)MK64_VISUAL_ASSET_ADDRESS;
    if(!recomp_vr_is_active() || assets->magic!=MK64_VISUAL_ASSET_MAGIC ||
        assets->version!=MK64_VISUAL_ASSET_VERSION || assets->end<MK64_VISUAL_ASSET_ADDRESS+sizeof(*assets) ||
        assets->end>0x80800000u) return 0;
    return assets;
}
/* Static visual import. Preserve retail actor visibility, shadow and simulation.
 * Blue shells and absent/older mods use the untouched original render leaves. */
int mk64_vr_render_item(Camera* camera, struct Actor* actor) {
    const Mk64VisualAssets* assets=mk64_vr_visual_assets();
    if(!assets || !(assets->flags & MK64_VISUAL_ITEMS)) return 0;
    const int banana=actor->type==ACTOR_BANANA;
    if(!banana && actor->type!=ACTOR_GREEN_SHELL && actor->type!=ACTOR_RED_SHELL) return 0;
    float distance=is_within_render_distance(camera->pos,actor->pos,camera->rot[1],0,
        gCameraZoom[camera-camera1],490000.0f);
    if(distance<0 || (banana && (actor->pos[1]>gCourseMaxY+800.f || actor->pos[1]<gCourseMinY-800.f))) {
        actor_not_rendered(camera,actor); return 1;
    }
    actor_rendered(camera,actor);
    const int held=mk64_vr_item_is_held(actor);
    if(!banana && distance<40000.f && !held) func_802979F8(actor,3.4f);
    Mat4 matrix;
    Vec3f pos={actor->pos[0],actor->pos[1]-(banana?2.f:0.f),actor->pos[2]};
    Vec3s rot={0,banana?0:((struct ShellActor*)actor)->rotVelocity,0};
    if(banana && actor->state==5) for(int i=0;i<3;i++)rot[i]=actor->rot[i];
    mtxf_pos_rotation_xyz(matrix,pos,rot);
    // Exact visual scales in Amped's custom renderers (804CAA18..804CAA2C).
    float size=banana && (actor->state==0 || actor->state==2 || actor->state==3)? .08f:.1f;
    if(banana && actor->state==5) {
        for(int j=0;j<3;j++) { matrix[0][j]*=.15f; matrix[1][j]*=.05f; matrix[2][j]*=.15f; }
    } else mtxf_scale(matrix,size);
    // The actor parent tags existing shell sprites as cylindrical billboards.
    // Every solid import overrides that tag, including after native release.
    u32 tag=held ? (banana?MK64_BANANA_GROUP:MK64_SHELL_GROUP) :
        (MK64_SOLID_ITEM_GROUP | ((u32)actor & 0xFFFFFFu));
    gEXMatrixGroupDecomposedNormal(gDisplayListHead++,tag,
        G_EX_PUSH,G_MTX_MODELVIEW,G_EX_EDIT_ALLOW);
    if(render_set_position(matrix,0)) {
        gEXPushGeometryMode(gDisplayListHead++);
        gEXPushOtherMode(gDisplayListHead++);
        gEXPushCombineMode(gDisplayListHead++);
        if(banana) {
            gSPDisplayList(gDisplayListHead++,(Gfx*)0x004C8818);
            gSPDisplayList(gDisplayListHead++,(Gfx*)0x004C7ED0);
        } else {
            gSPDisplayList(gDisplayListHead++,(Gfx*)0x004C9158);
            gSPDisplayList(gDisplayListHead++,(Gfx*)0x004C8C48);
            if(actor->type==ACTOR_GREEN_SHELL) func_8004B35C(15,190,50,255);
            else func_8004B35C(240,35,20,255);
            gSPDisplayList(gDisplayListHead++,(Gfx*)0x004C8AB8);
        }
        gDPPipeSync(gDisplayListHead++);
        gEXPopCombineMode(gDisplayListHead++);
        gEXPopOtherMode(gDisplayListHead++);
        gEXPopGeometryMode(gDisplayListHead++);
    }
    gEXPopMatrixGroup(gDisplayListHead++,G_MTX_MODELVIEW);
    return 1;
}
