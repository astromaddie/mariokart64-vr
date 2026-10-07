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
