#ifndef MK64_ARM_RIG_H
#define MK64_ARM_RIG_H
/* Standard Amped v3.21 armature calibration. Joint translations are authored
 * model units; distal pivots are geometry estimates, adjustable through seat/world scale.
 * The artwork, materials and vertices are supplied privately by the importer. */
typedef struct Mk64ArmRig {
    float base[3], shoulder[3], elbow[3], wrist[3], eye_height;
} Mk64ArmRig;
static const Mk64ArmRig mk64_arm_rigs[8] = {
    {{0,480,-160},{260,310,-30},{0,-80,150},{-10,25,486},6.13f},
    {{0,480,-160},{210,310,-30},{30,-80,150},{-9,25,486},6.25f},
    {{0,480,-160},{130,360,20},{30,-90,170},{28,3,337},6.37f},
    {{0,400,70},{90,280,0},{110,-20,170},{-39,39,139},5.48f},
    {{0,310,-270},{280,850,90},{160,-210,340},{-98,-102,380},7.50f},
    {{0,480,-160},{190,400,20},{200,-160,100},{-101,61,499},6.48f},
    {{0,510,-80},{160,360,-20},{80,-110,170},{-28,-28,380},6.39f},
    {{0,390,-280},{330,670,220},{0,-160,170},{-125,-121,351},8.12f}
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
    if(character==3 && !lower) t=(z-80.0f)/229.0f;
    else t=(z-mk64_arm_rigs[character].wrist[2]*.40f)/(mk64_arm_rigs[character].wrist[2]*.45f);
    if(t<0)t=0; if(t>1)t=1;
    return (int)(t*31.0f+.5f);
}
#endif
