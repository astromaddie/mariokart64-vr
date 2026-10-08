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
#ifdef __cplusplus
extern "C" {
void mk64_vr_publish_interaction(const Mk64VRInteraction* state);
void mk64_vr_get_racer(struct Mk64Frame* state);
}
#endif
#endif
