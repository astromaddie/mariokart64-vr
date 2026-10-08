#ifndef MK64_ARM_RIG_H
#define MK64_ARM_RIG_H
/* Standard Amped v3.21 armature calibration. Joint translations are authored
 * model units; grip pivots are triangle-referenced hand-region estimates (not fingertip bounds).
 * The artwork, materials and vertices are supplied privately by the importer. */
typedef struct Mk64ArmRig {
    float base[3], shoulder[3], elbow[3], wrist[3], eye_height, grip_forward;
} Mk64ArmRig;
/* Grasp contact lies forward of the palm centre in source hand coordinates.
 * 50 source units = 2.5 cm at native .005 scale / world_scale 10. Toad's smaller
 * hand caps this at 28 units, inside its triangle-referenced Z=279 fingertip bound. */
static const Mk64ArmRig mk64_arm_rigs[8] = {
    {{0,480,-160},{260,310,-30},{0,-80,150},{12,-9,291},6.13f,50},
    {{0,480,-160},{210,310,-30},{30,-80,150},{10,-9,291},6.25f,50},
    {{0,480,-160},{130,360,20},{30,-90,170},{35,26,246},6.37f,50},
    {{0,400,70},{90,280,0},{110,-20,170},{-4,57,77},5.48f,28},
    {{0,310,-270},{280,850,90},{160,-210,340},{-278,-20,273},7.50f,50},
    {{0,480,-160},{190,400,20},{200,-160,100},{-96,86,337},6.48f,50},
    {{0,510,-80},{160,360,-20},{80,-110,170},{-15,-7,243},6.39f,50},
    {{0,390,-280},{330,670,220},{0,-160,170},{-104,-154,216},8.12f,50}
};
#define MK64_ARM_GROUP 0x71000000u
#define MK64_ITEM_GROUP 0x74000000u
#define MK64_WHEEL_GROUP 0x72000000u
#define MK64_KART_GROUP 0x73000000u
#define MK64_KART_ANCHOR 0x73000001u
/* Upper nodes keep a rigid upper transform except Toad's combined mesh.
 * Forearms smoothly turn into the separately oriented distal hand. 32 bins avoid
 * one matrix per source vertex, while retaining every original vertex/UV/triangle. */
static inline int mk64_arm_weight(int character, int lower, float z) {
    float t;
    if (!lower && character != 3) return 0;
    if(character==3 && !lower) t=(z-80.0f)/(mk64_arm_rigs[character].elbow[2]+mk64_arm_rigs[character].wrist[2]-80.0f);
    else t=(z-mk64_arm_rigs[character].wrist[2]*.40f)/(mk64_arm_rigs[character].wrist[2]*.45f);
    if(t<0)t=0; if(t>1)t=1;
    return (int)(t*31.0f+.5f);
}
#endif
