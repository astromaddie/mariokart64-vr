#ifndef MK64_FIRST_PERSON_H
#define MK64_FIRST_PERSON_H
/* Fixed 32-bit exchange between MIPS simulation and display-time VR input.
 * Positions/quaternions are in seat axes (+X right, +Y up, -Z forward), game units.
 * Launch velocity is game units per native 30 Hz tick, never inferred from kart motion. */
typedef struct Mk64VRInteraction {
    unsigned int serial;
    int enabled, hand_valid[2], wheel_hands, item_hand;
    int command; /* 0 none, 1 take item, 2 release, 3 cancel pending command */
    int rear, diagnostic_item;
    float hand_pos[2][3], hand_rot[2][4];
    float velocity[3], wheel_angle, world_scale, seat_height, seat_forward;
} Mk64VRInteraction;
/* Shared held-prop calibration, in tracked hand axes: +Y above palm, -Z forward.
 * Keep the raw hand pose untouched for arm IK, steering and gesture detection. */
static inline void mk64_vr_rotate_hand_vector(float out[3], const float q[4], const float v[3]) {
    float norm=q[0]*q[0]+q[1]*q[1]+q[2]*q[2]+q[3]*q[3];
    float k=norm>.00001f ? 2.f/norm : 0.f;
    float cross[3]={q[1]*v[2]-q[2]*v[1],q[2]*v[0]-q[0]*v[2],q[0]*v[1]-q[1]*v[0]};
    out[0]=v[0]+k*(q[3]*cross[0]+q[1]*cross[2]-q[2]*cross[1]);
    out[1]=v[1]+k*(q[3]*cross[1]+q[2]*cross[0]-q[0]*cross[2]);
    out[2]=v[2]+k*(q[3]*cross[2]+q[0]*cross[1]-q[1]*cross[0]);
}
static inline void mk64_vr_held_item_anchor(float out[3], const float hand[3], const float q[4],
    int actor_type, float world_scale) {
    float offset[3]={0,0,0}, rotated[3];
    if(actor_type==6)offset[1]=.40f*world_scale; /* banana */
    else if(actor_type==7 || actor_type==8) {offset[1]=.40f*world_scale;offset[2]=-.24f*world_scale;}
    mk64_vr_rotate_hand_vector(rotated,q,offset);
    for(int i=0;i<3;i++)out[i]=hand[i]+rotated[i];
}
#ifdef __cplusplus
extern "C" {
void mk64_vr_publish_interaction(const Mk64VRInteraction* state);
void mk64_vr_get_racer(struct Mk64Frame* state);
}
#endif
#endif
