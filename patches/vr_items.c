#include "patches.h"
#include "main.h"
#define CAMERA_H
#define CODE_800029B0_H
#include "actors.h"
extern void delete_actor_in_unexpired_actor_list(s32);
extern s32 add_red_shell_in_unexpired_actor_list(s32);
extern s32 add_green_shell_in_unexpired_actor_list(s32);
extern s32 add_blue_shell_in_unexpired_actor_list(s32);
#include "audio/external.h"
#include "racing/actors_extended.h"
#include "update_objects.h"
#include "../include/mk64_first_person.h"
extern void recomp_mk64_vr_interaction(Mk64VRInteraction* state);
extern int recomp_vr_is_active(void);
Mk64VRInteraction mk64_vr_interaction;
static int held_index = -1, held_type;
static volatile unsigned char rear_red[ACTOR_LIST_SIZE];

static int held_valid(void) {
    if (held_index < 0) return 0;
    struct Actor* actor = &gActorList[held_index];
    if (!(actor->flags & 0x8000) || actor->type != held_type || actor->state != 0) {
        held_index=-1; return 0;
    }
    return 1;
}
int mk64_vr_item_is_held(struct Actor* actor) { return mk64_vr_interaction.enabled && held_valid() && actor==&gActorList[held_index]; }
int mk64_vr_held_item(void) { return held_valid() ? held_type : 0; }
static void seat_vector(float out[3], const float in[3]) {
    // Native launch axes are left/up/forward; tracked seat axes are right/up/back.
    out[0]=-in[0]; out[1]=in[1]; out[2]=-in[2];
    func_802B64C4(out, gPlayers[0].rotation[1]+gPlayers[0].unk_0C0);
}
static void hand_position(struct Actor* actor) {
    int hand=mk64_vr_interaction.item_hand;
    if (hand < 0 || hand > 1 || !mk64_vr_interaction.hand_valid[hand]) return;
    float local[3], world[3];
    for(int i=0;i<3;i++) local[i]=mk64_vr_interaction.hand_pos[hand][i];
    local[1]+=mk64_vr_interaction.seat_height;
    local[2]-=mk64_vr_interaction.seat_forward;
    seat_vector(world,local);
    for(int i=0;i<3;i++) actor->pos[i]=gPlayers[0].pos[i]+world[i];
    copy_collision(&gPlayers[0].collision, &actor->unk30);
}
void mk64_vr_tick(void) {
    recomp_mk64_vr_interaction(&mk64_vr_interaction);
    const int race = gGamestate==4 && gActiveScreenMode==0 && !gDemoMode && gCourseTimer>0;
    if (!race) { held_index=-1; for(int i=0;i<ACTOR_LIST_SIZE;i++) rear_red[i]=0; return; }
    if (!recomp_vr_is_active() || !mk64_vr_interaction.enabled || gIsGamePaused) return;
    Player* player=&gPlayers[0];
    if (mk64_vr_interaction.command==1 && !held_valid()) {
        int index=-1;
        // Only the host's bounded force-render synthetic sequence sets this field.
        if (player->currentItemCopy==ITEM_NONE && (mk64_vr_interaction.diagnostic_item==ITEM_BANANA ||
            mk64_vr_interaction.diagnostic_item==ITEM_GREEN_SHELL || mk64_vr_interaction.diagnostic_item==ITEM_RED_SHELL))
            player->currentItemCopy=mk64_vr_interaction.diagnostic_item;
        if(player->currentItemCopy==ITEM_GREEN_SHELL) index=use_green_shell_item(player);
        if(player->currentItemCopy==ITEM_RED_SHELL) index=use_red_shell_item(player);
        if(player->currentItemCopy==ITEM_BANANA) index=use_banana_item(player);
        if(index>=0) { held_index=index; held_type=gActorList[index].type; rear_red[index]=0; consume_item(0);
            recomp_printf("[vr-item] held type=%d hand=%d actor=%d address=%08x\n",held_type,mk64_vr_interaction.item_hand,held_index,(unsigned)&gActorList[index]); }
    }
    if (!held_valid()) return;
    struct Actor* actor=&gActorList[held_index];
    hand_position(actor);
    if (mk64_vr_interaction.command!=2) return;
    float local[3];
    for(int i=0;i<3;i++) local[i]=mk64_vr_interaction.velocity[i];
    if (mk64_vr_interaction.rear) {
        // Rear is defined by the kart seat, independent of HMD yaw or gesture direction.
        local[0]=0; local[1]=held_type==ACTOR_BANANA?1.5f:0;
        local[2]=held_type==ACTOR_BANANA?0:8.0f;
        float behind[3]={0,1,player->boundingBoxSize+4};
        float world[3]; seat_vector(world,behind);
        for(int i=0;i<3;i++) actor->pos[i]=player->pos[i]+world[i];
    } else if(local[0]*local[0]+local[1]*local[1]+local[2]*local[2]<.0001f) {
        local[1]=held_type==ACTOR_BANANA?1.5f:0;
        local[2]=held_type==ACTOR_BANANA?0:-(mk64_vr_interaction.world_scale * 0.15f / 30.0f);
    }
    seat_vector(actor->velocity,local);
    if(held_type==ACTOR_BANANA) {
        struct BananaActor* banana=(struct BananaActor*)actor;
        banana->state=DROPPED_BANANA; banana->unk_04=180;
        player->soundEffects &= ~HOLD_BANANA_SOUND_EFFECT;
        func_800C9060(0,SOUND_ARG_LOAD(0x19,0x00,0x80,0x12));
    } else {
        struct ShellActor* shell=(struct ShellActor*)actor;
        shell->state=MOVING_SHELL; shell->someTimer=30;
        if(held_type==ACTOR_RED_SHELL) {
            rear_red[held_index]=mk64_vr_interaction.rear!=0;
            add_red_shell_in_unexpired_actor_list(held_index);
        } else add_green_shell_in_unexpired_actor_list(held_index);
        func_800C9060(0,SOUND_ARG_LOAD(0x19,0x00,0x80,0x04));
        func_800C90F4(0,(player->characterId*0x10)+SOUND_ARG_LOAD(0x29,0x00,0x80,0x00));
    }
    recomp_printf("[vr-item] release type=%d rear=%d velocity=%.3f,%.3f,%.3f actor=%d\n",held_type,mk64_vr_interaction.rear,actor->velocity[0],actor->velocity[1],actor->velocity[2],held_index);
    held_index=-1;
}

// Compile the authoritative native state machines verbatim under private names.
// Wrappers intercept only the one tracked held actor and marked rear red shots.
#define update_actor_green_shell mk64_native_green_shell
#include "../lib/mk64/src/actors/green_shell/update.inc.c"
#undef update_actor_green_shell
void mk64_native_red_collision(struct ShellActor* shell);
#define func_802B3B44 mk64_native_red_path
#define func_802B3E7C mk64_native_red_seek
#define func_802B3FD0 mk64_native_red_target
#define func_802B4104 mk64_native_red_collision
#define update_actor_red_blue_shell mk64_native_red_shell
#include "../lib/mk64/src/actors/blue_and_red_shells/update.inc.c"
#undef update_actor_red_blue_shell
#undef func_802B3B44
#undef func_802B3E7C
#undef func_802B3FD0
#undef func_802B4104
#define update_actor_banana mk64_native_banana
#include "../lib/mk64/src/actors/banana/update.inc.c"
#undef update_actor_banana
static int retained(struct Actor* actor) {
    return mk64_vr_interaction.enabled && held_valid() && actor==&gActorList[held_index];
}
RECOMP_PATCH void update_actor_green_shell(struct ShellActor* shell) {
    if(retained((struct Actor*)shell)) return;
    mk64_native_green_shell(shell);
}
RECOMP_PATCH void update_actor_banana(struct BananaActor* banana) {
    if(retained((struct Actor*)banana)) return;
    mk64_native_banana(banana);
}
RECOMP_PATCH void update_actor_red_blue_shell(struct ShellActor* shell) {
    if(retained((struct Actor*)shell)) return;
    int index=(struct Actor*)shell-gActorList;
    if(rear_red[index] && shell->type==ACTOR_RED_SHELL && shell->state==MOVING_SHELL) {
        // Native red MOVING_SHELL handles ballistic integration/collision but enters
        // homing at timer zero. Bypass only that transition; expire owner immunity.
        int timer=shell->someTimer;
        shell->someTimer=2;
        mk64_native_red_shell(shell);
        shell->someTimer=timer>0?timer-1:0;
        if(shell->someTimer==0) shell->flags &= ~0x1000;
    } else { rear_red[index]=0; mk64_native_red_shell(shell); }
}

// Native destruction path; clear tracked ownership before the slot can be reused.
RECOMP_PATCH void destroy_actor(struct Actor* actor) {
    int vr_index=actor-gActorList;
    if (held_index==vr_index) held_index=-1;
    if (vr_index>=0 && vr_index<ACTOR_LIST_SIZE) rear_red[vr_index]=0;

    play_sound_before_despawn(actor);
    actor->flags = 0;
    actor->type = 0;
    gNumActors--;
}

// Native destruction path; clear tracked ownership before the slot can be reused.
RECOMP_PATCH void destroy_destructable_actor(struct Actor* actor) {
    int vr_index=actor-gActorList;
    if (held_index==vr_index) held_index=-1;
    if (vr_index>=0 && vr_index<ACTOR_LIST_SIZE) rear_red[vr_index]=0;

    struct ShellActor* shell;
    struct BananaActor* banana;
    struct FakeItemBox* fakeItemBox;
    Player* player;

    switch (actor->type) {
        case ACTOR_BANANA:
            banana = (struct BananaActor*) actor;
            switch (banana->state) {
                case FIRST_BANANA_BUNCH_BANANA:
                case BANANA_BUNCH_BANANA:
                    destroy_banana_in_banana_bunch(banana);
                    break;
                case HELD_BANANA:
                    player = &gPlayers[banana->playerId];
                    player->soundEffects &= ~0x00040000;
                    /* fallthrough */
                case BANANA_ON_GROUND:
                    banana->flags = -0x8000;
                    banana->unk_04 = 0x003C;
                    banana->state = DESTROYED_BANANA;
                    banana->velocity[1] = 3.0f;
                    break;
                case DROPPED_BANANA:
                case DESTROYED_BANANA:
                default:
                    break;
            }
            break;
        case ACTOR_GREEN_SHELL:
            shell = (struct ShellActor*) actor;
            if (shell->state != GREEN_SHELL_HIT_A_RACER) {
                switch (shell->state) {
                    case MOVING_SHELL:
                        delete_actor_in_unexpired_actor_list(actor - gActorList);
                        /* fallthrough */
                    case HELD_SHELL:
                    case RELEASED_SHELL:
                        shell->flags = -0x8000;
                        shell->rotAngle = 0;
                        shell->someTimer = 0x003C;
                        shell->state = GREEN_SHELL_HIT_A_RACER;
                        shell->velocity[1] = 3.0f;
                        break;
                    case TRIPLE_GREEN_SHELL:
                        triple_shell_actor_collide_with_player(shell, ACTOR_GREEN_SHELL);
                        break;
                    default:
                        break;
                }
            }
            break;
        case ACTOR_BLUE_SPINY_SHELL:
            shell = (struct ShellActor*) actor;
            if (shell->state != DESTROYED_SHELL) {
                switch (shell->state) {
                    case MOVING_SHELL:
                    case RED_SHELL_LOCK_ON:
                    case TRIPLE_GREEN_SHELL:
                    case GREEN_SHELL_HIT_A_RACER:
                    case BLUE_SHELL_LOCK_ON:
                    case BLUE_SHELL_TARGET_ELIMINATED:
                        func_800C9EF4(shell->pos, SOUND_ARG_LOAD(0x51, 0x01, 0x80, 0x08));
                        delete_actor_in_unexpired_actor_list(actor - gActorList);
                        /* fallthrough */
                    case HELD_SHELL:
                    case RELEASED_SHELL:
                        shell->flags = -0x8000;
                        shell->rotAngle = 0;
                        shell->someTimer = 0x003C;
                        shell->state = DESTROYED_SHELL;
                        shell->velocity[1] = 3.0f;
                        break;
                    default:
                        break;
                }
            }
            break;
        case ACTOR_RED_SHELL:
            shell = (struct ShellActor*) actor;
            if (shell->state != DESTROYED_SHELL) {
                switch (shell->state) {
                    case MOVING_SHELL:
                    case RED_SHELL_LOCK_ON:
                    case TRIPLE_GREEN_SHELL:
                    case GREEN_SHELL_HIT_A_RACER:
                    case BLUE_SHELL_LOCK_ON:
                    case BLUE_SHELL_TARGET_ELIMINATED:
                        delete_actor_in_unexpired_actor_list(actor - gActorList);
                        /* fallthrough */
                    case HELD_SHELL:
                    case RELEASED_SHELL:
                        shell->flags = -0x8000;
                        shell->rotAngle = 0;
                        shell->someTimer = 0x003C;
                        shell->state = DESTROYED_SHELL;
                        shell->velocity[1] = 3.0f;
                        break;
                    case TRIPLE_RED_SHELL:
                        triple_shell_actor_collide_with_player(shell, ACTOR_RED_SHELL);
                        break;
                    default:
                        break;
                }
            }
            break;
        case ACTOR_FAKE_ITEM_BOX:
            fakeItemBox = (struct FakeItemBox*) actor;
            player = &gPlayers[(s16) fakeItemBox->playerId];
            if (fakeItemBox->state == HELD_FAKE_ITEM_BOX) {
                player->soundEffects &= ~0x00040000;
            }
            fakeItemBox->state = DESTROYED_FAKE_ITEM_BOX;
            fakeItemBox->flags = -0x8000;
            fakeItemBox->someTimer = 0;
            break;
    }
}
