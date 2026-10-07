#ifndef MK64_FRAME_H
#define MK64_FRAME_H
// Fixed 32-bit ABI shared by the MIPS patches and native host. No pointers or bools.
typedef struct Mk64Frame {
    unsigned int frame;
    int game_state, screen_mode, demo, paused, course, global_timer;
    float race_time;
    float eye[3], at[3], up[3], fov, near_z, far_z;
    float player_pos[8][3], player_speed[8];
    int player_lap[8], player_rank[8];
} Mk64Frame;
#endif
