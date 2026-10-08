#!/usr/bin/env python3
"""Check the production display-list boundaries that RT64's classifiers consume.
This is source-contract coverage, not a substitute for actual eye-image inspection.
"""
from pathlib import Path
import re
root = Path(__file__).resolve().parents[3]
source = (root / "patches/camera.c").read_text()
# Function boundaries, not preprocessor boundaries: VERSION_EU has an internal #endif.
body = source.split("RECOMP_PATCH void render_player_one_1p_screen(void) {", 1)[1].split(
    "RECOMP_PATCH void render_player_one_2p_screen_vertical", 1)[0]
assert "const int vr_world = mk64_vr_world();" in body
sky = body.index("if (vr_world) func_802A53A4();")
world = body.index("0xFFFFAAAA")
flat_sky = body.index("if (!vr_world) func_802A53A4();")
projection = body.index("guPerspective(")
hud = body.index("if (vr_world) gEXMatrixGroupSimple(gDisplayListHead++, 0xFFFFAAE1")
assert sky < world < flat_sky < projection < body.index("render_course(") < hud < body.index("func_80058BF4();")
# Both interpolation branches must restore the world group after sky rendering.
assert body.count("0xFFFFAAAA") == 2
profile = (root / "src/vr/game/mk64_profile.c").read_text()
assert re.search(r"camera_groups\[\].*0xFFFFAAAAu, 0xFFFFAAE0u", profile)
assert "0xFFFFAAE1" not in profile
# Never widen the shared player-camera collision function: AI uses it too.
current = (root / "patches/render_distance.c").read_text().split(
    "RECOMP_PATCH u16 check_player_camera_collision", 1)[1].split("#endif", 1)[0]
assert "mk64_vr" not in current and "recomp_mk64_vr_yaw" not in current
print("production render boundaries: sky/world/HUD and collision isolation passed")
# Every immersive projection uses the full native framebuffer; native race intros use cinema.
assert body.index("if (vr_world) mk64_vr_full_viewport();") < body.index("guPerspective(")
render = (root / "patches/vr_render.h").read_text()
assert "gCourseTimer > 0.0f" in render
scene = (root / "src/vr/game/mk64_scene.h").read_text()
assert "state.race_time <= 0.0f ? DK64VR_SCENE_CUTSCENE" in scene
assert "VIRTUAL_TO_PHYSICAL(&D_802B8880)" in render
assert "G_SC_NON_INTERLACE, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT" in render
sky = (root / "patches/vr_sky.c").read_text()
clouds = sky.split("void mk64_vr_clouds(s32 start)", 1)[1]
assert clouds.index("mk64_vr_full_viewport();") < clouds.index("&sky_projection[slot]") < clouds.index("gSPVertex(")
assert clouds.index("&sky_view[slot]") < clouds.index("gSPVertex(")
# A delayed HUD workload must retain the capture's yaw until the pixels are recorded.
host = (root / "src/vr/xr/xr_host.cpp").read_text()
assert "diagYawStepPending && (!hudDumpDue || lastInfo.hudCalls == 0)" in host
assert 'name == "vr-hud" ? hudDumpYawDeg : diagYawDeg' in host
assert 'envFlag("RT64_VR_HIDDEN_MASK", false)' in host
print("immersive viewport/cloud projection and deferred HUD pose contracts passed")

# Sprite tags must cover vertices and exclude neighbouring real 3D geometry.
billboards = (root / "patches/vr_billboards.c").read_text()
for name in ("func_800431B0", "draw_2d_texture_at", "func_80048130", "func_800484BC",
             "func_800485C4", "func_800468E0"):
    leaf = re.search(r"RECOMP_PATCH void " + name + r"\(.*?\n}", billboards, re.S)[0]
    assert leaf.index("sprite_begin(") < leaf.index("rsp_set_matrix_transformation(") < leaf.index("sprite_end();")
    assert leaf.rindex("gSP", 0, leaf.index("sprite_end();")) > leaf.index("sprite_begin(")
shadow = re.search(r"RECOMP_PATCH void func_8029794C\(.*?\n}", billboards, re.S)[0]
assert "TAG_OBJECT(pos)" in shadow and "TAG_WORLD" not in shadow
palms = re.search(r"RECOMP_PATCH void render_palm_trees\(.*?\n}", billboards, re.S)[0]
assert palms.index("if (test == 6)") < palms.index("TAG_WORLD_ACTOR(var_s1)")
assert "if (test != 6) sprite_end();" in palms
objects = (root / "patches/object_tagging.c").read_text()
actors = objects.split("RECOMP_PATCH void render_course_actors", 1)[1].split("switch (actor->type)", 1)[1].split("actorTag = TAG_WORLD_ACTOR", 1)[0]
for actor in ("COW", "TREE_MOO_MOO_FARM", "TREE_FRAPPE_SNOWLAND", "GREEN_SHELL", "PIRANHA_PLANT"):
    assert "case ACTOR_" + actor + ":" in actors
for actor in ("PALM_TREE", "BANANA", "YOSHI_EGG", "TRAIN_ENGINE"):
    assert "case ACTOR_" + actor + ":" not in actors
assert "#if 1\nRECOMP_PATCH void render_cows" in objects
assert "((var_s1 - var_t1) << 2)" in objects  # identity per cow, not per repeated texture
hud = (root / "patches/hud.c").read_text()
normal_timer = hud.split("RECOMP_PATCH void print_timer", 1)[1]
assert "func_8004F950(x, y, 255, time);" in normal_timer
assert normal_timer.index("if (mk64_vr_world())") < normal_timer.index("func_8004F950") < normal_timer.index("else") < normal_timer.index("func_8004F774")
for name in ("func_80055AB8", "func_800563DC", "func_8005669C", "func_80056BF0", "func_80056E24"):
    owner = re.search(r"RECOMP_PATCH void " + name + r"\(.*?\n}", billboards, re.S)[0]
    assert "sprite_owner = 0x62" in owner and "sprite_owner = 0;" in owner
assert "sprite_owner + ++sprite_slot" in billboards
assert "sprite_slot = 16;" in billboards  # battle wheels follow body/fuse slots

native_draw = (root / "lib/mk64/src/render_objects.c").read_text()
assert "func_8004BA98(phi_s1, arg1, 8, 16, D_801657D0[i] * 8, 0, 1);" in native_draw
assert "phi_s1 += 8;" in native_draw
print("sprite-only tags, shadow/model exclusions and complete timer-cell path passed")

# Reproducible scenes are process-only and bounded; effect activation uses the
# actual game item path, never an effect flag or a second palette tick.
frame_api = (root / "src/game/frame_api.cpp").read_text()
assert 'std::getenv("MK64_DIAG_AUTOSTART")' in frame_api
frame = (root / "patches/frame_report.c").read_text()
assert "gGamestate != 4 && gGamestateNext == 4 && !gDemoMode" in frame
assert "apply_star_sound_effect(&gPlayers[0], 0);" in frame
assert "frame <= (unsigned int)limit" in frame
assert "stats->commands < 8192" in frame and "depth > 16" in frame
assert objects.index("Gfx* racer_start") < objects.index("render_kart(player") < objects.index("mk64_diag_racer(player")
print("bounded native scene/effect and production racer draw diagnostics passed")
