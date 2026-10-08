#!/usr/bin/env python3
"""Exercise production diagnostic selection and retail GP grid/AI setup."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]


def function(source, name):
    start = source.index("void " + name + "(")
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


patch = (root / "patches/frame_report.c").read_text()
spawn = (root / "lib/mk64/src/spawn_players.c").read_text()
menus = (root / "lib/mk64/src/menus.c").read_text()
controller = (root / "lib/mk64/src/player_controller.c").read_text()
course_header = (root / "lib/mk64/include/course.h").read_text()
defines = (root / "lib/mk64/include/defines.h").read_text()
courses = re.search(r"typedef enum \{.*?\} COURSES;", course_header, re.S)[0]
cup_order = re.search(r"const s16 gCupCourseOrder\[5\]\[4\] = \{.*?\};", menus, re.S)[0]
ai_tables = controller[controller.index("s16 gKartAIforMario[]"):controller.index("s16 gKartAIforMarioAndLuigi[]")]
macro_names = ["MARIO", "LUIGI", "YOSHI", "TOAD", "DK", "WARIO", "PEACH", "BOWSER",
               "PLAYER_HUMAN_AND_KART_AI", "PLAYER_EXISTS", "PLAYER_KART_AI", "PLAYER_START_SEQUENCE",
               "PLAYER_STAGING", "PLAYER_HUMAN"]
macros = "\n".join(re.search(r"^#define " + name + r"\s+.*$", defines, re.M)[0] for name in macro_names)
setup = function((root / "lib/mk64/src/code_800029B0.c").read_text(), "setup_race")
# Execute the actual setup prefix through course selection, before loading GPU
# assets/collision. The complete stock grid and AI selection routines follow.
setup = setup[:setup.index("    gActiveScreenMode =")] + "}\n"
program = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
typedef int16_t s16; typedef int8_t s8; typedef uint16_t u16; typedef int32_t s32; typedef float f32;
typedef struct { unsigned characterId; } Player;
enum { GRAND_PRIX=0, COURSE_ONE=0, NUM_PLAYERS=8, RACING=4, DEBUG_MENU_OPTION_SELECTED=0x40 };
int gGamestate, gGamestateNext=4, gDemoMode, gIsGamePaused, gActiveScreenMode;
int gModeSelection=GRAND_PRIX, gCourseIndexInCup, gCupSelection, gCurrentCourseId=8;
int gDebugMenuSelection=3, D_8016556E, D_80164A28, gGPCurrentRaceRankByPlayerId[8], D_80165270[8];
int gPlayerCountSelection1, gPlayerCount=1, gIsMirrorMode;
float gCourseTimer, gCourseDirection;
s8 gCharacterSelections[4]; s16 chooseKartAIPlayers[7];
Player gPlayers[8];
Player *gPlayerOneCopy=&gPlayers[0], *gPlayerTwo=&gPlayers[1], *gPlayerThree=&gPlayers[2],
    *gPlayerFour=&gPlayers[3], *gPlayerFive=&gPlayers[4], *gPlayerSix=&gPlayers[5],
    *gPlayerSeven=&gPlayers[6], *gPlayerEight=&gPlayers[7];
int mk64_diag_racers_enabled, options[4];
int recomp_mk64_diag_option(int index) { return options[index]; }
#define recomp_printf(...) ((void)0)
void apply_star_sound_effect(Player* p, s8 index) { assert(0); }
int random_int(int max) { static int seed; return seed++ % max; }
void func_80039AE4(void) {}
void spawn_player(Player* p, s8 index, f32 row, f32 column, f32 height, f32 angle, u16 character, s16 type) {
    assert(character<8); assert(index>=0 && index<8); p->characterId=character;
}
''' + macros + "\n" + courses + "\n" + cup_order + "\n" + ai_tables + "\n" + setup + "\n"
program += function(patch, "diagnostic_scene") + "\n" + function(spawn, "func_80039DA4") + "\n" + function(spawn, "spawn_players_gp_one_player")
program += r'''
int main(int argc, char** argv) {
    const int character=atoi(argv[1]), course=atoi(argv[2]), mode=atoi(argv[3]);
    options[0]=character; options[1]=course; options[2]=-1; options[3]=mode==3 ? -1 : 2700;
    diagnostic_scene(612);
    if (mode==3) { assert(gCharacterSelections[0]==0 && gCurrentCourseId==8 && gDebugMenuSelection==3); return 0; }
    assert(gCharacterSelections[0]==character && gCurrentCourseId==course);
    assert(gDebugMenuSelection==DEBUG_MENU_OPTION_SELECTED);
    if (mode==1 || mode==2) {
        if (mode==1) gGamestateNext=0;
        diagnostic_scene(mode==1 ? 613 : 2701);
        assert(gDebugMenuSelection==3); return 0;
    }
    if (mode==4) gDebugMenuSelection=3; // reproduce the previous missing fresh-entry flag
    setup_race(); assert(gCurrentCourseId==course);
    float rows[8]={0,1,2,3,4,5,6,7}, columns[8]={0,1,2,3,4,5,6,7};
    spawn_players_gp_one_player(rows,columns,0);
    unsigned characters=0, grid=0;
    for (int i=0;i<8;i++) { characters |= 1u<<gPlayers[i].characterId; grid |= 1u<<D_80165270[i]; }
    if (mode==4) { assert(characters!=255 && grid!=255); return 0; }
    assert(characters==255 && grid==255 && gPlayers[0].characterId==character);
    gGamestate=4; diagnostic_scene(613); assert(gDebugMenuSelection==3);
}
'''
with tempfile.TemporaryDirectory(prefix="mk64-diagnostic-scene-") as directory:
    code, binary = Path(directory) / "scene.c", Path(directory) / "scene"
    code.write_text(program)
    subprocess.run(["cc", "-std=c11", str(code), "-o", str(binary)], check=True)
    course_ids = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,18]
    for character in range(8):
        for course in course_ids:
            subprocess.run([str(binary),str(character),str(course),"0"], check=True)
    for mode in (1,2,3,4):
        subprocess.run([str(binary),"7","0",str(mode)], check=True)
print("production diagnostic + retail GP setup: 128 character/course grids, restore/cancel/expiry/default and prior failure passed")
