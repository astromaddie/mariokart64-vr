# Host unit tests for the VR bridge (with DK64's profile, test_profile_dk64.c), buildable on their own (no ROM, no recompiled code):
#   cmake -S src/vr/tests -B build-vrtest && cmake --build build-vrtest && build-vrtest/dk64vr_tests
cmake_minimum_required(VERSION 3.20)
project(dk64vr_tests LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 11)

set(DK64VR_ROOT ${CMAKE_CURRENT_LIST_DIR}/../../..)
add_executable(dk64vr_tests
    ${CMAKE_CURRENT_LIST_DIR}/dk64vr_tests.cpp
    ${DK64VR_ROOT}/src/vr/bridge/dk64vr_math.cpp
    ${DK64VR_ROOT}/src/vr/bridge/dk64vr_camsmooth.cpp
    ${DK64VR_ROOT}/src/vr/bridge/dk64vr_foveation.cpp
    ${DK64VR_ROOT}/src/vr/bridge/dk64vr_sched.cpp
    ${DK64VR_ROOT}/src/vr/bridge/dk64vr_settings.c
    ${DK64VR_ROOT}/src/vr/bridge/dk64vr_log.c
    ${DK64VR_ROOT}/src/vr/bridge/dk64vr_input.cpp
    ${DK64VR_ROOT}/src/vr/menu/dk64vr_menu.cpp
    ${CMAKE_CURRENT_LIST_DIR}/test_profile_dk64.c
    ${DK64VR_ROOT}/src/vr/game/profile_ext_default.c
    ${DK64VR_ROOT}/third_party/sfvr/src/sfvr_settings.c
    ${DK64VR_ROOT}/third_party/sfvr/src/sfvr_adjust.c
    ${DK64VR_ROOT}/third_party/sfvr/src/sfvr_camera.c
    ${DK64VR_ROOT}/third_party/sfvr/src/sfvr_view.c
    ${DK64VR_ROOT}/third_party/sfvr/src/sfvr_turn.c
    ${DK64VR_ROOT}/third_party/sfvr/src/sfvr_haptics.c)
target_include_directories(dk64vr_tests PRIVATE ${DK64VR_ROOT}/src/vr/include ${DK64VR_ROOT}/src/vr/bridge ${DK64VR_ROOT}/src/vr/menu ${DK64VR_ROOT}/third_party/sfvr/include ${DK64VR_ROOT}/lib/rt64/src)
target_compile_options(dk64vr_tests PRIVATE -Wall -Wextra -ffp-contract=off)
target_link_libraries(dk64vr_tests PRIVATE m)
enable_testing()
add_test(NAME dk64vr_tests COMMAND dk64vr_tests)
add_executable(mk64_profile_tests mk64_profile_tests.cpp
    ../game/mk64_profile.c ../bridge/dk64vr_settings.c ../bridge/dk64vr_log.c
    ../bridge/dk64vr_input.cpp
    ../../../third_party/sfvr/src/sfvr_settings.c ../../../third_party/sfvr/src/sfvr_view.c
    ../../../third_party/sfvr/src/sfvr_turn.c)
target_include_directories(mk64_profile_tests PRIVATE ../../../include ../include ../bridge
    ../../../third_party/sfvr/include)
target_compile_definitions(mk64_profile_tests PRIVATE VR_GAME_RACER=1)
target_compile_options(mk64_profile_tests PRIVATE -Wall -Wextra -ffp-contract=off)
add_test(NAME mk64_profile_tests COMMAND mk64_profile_tests)
add_executable(rt64_vr_eye_slots_test ${DK64VR_ROOT}/lib/rt64/src/tests/rt64_vr_eye_slots_test.cpp)
target_include_directories(rt64_vr_eye_slots_test PRIVATE ${DK64VR_ROOT}/lib/rt64/src)
target_compile_options(rt64_vr_eye_slots_test PRIVATE -Wall -Wextra)
add_test(NAME rt64_vr_eye_slots_test COMMAND rt64_vr_eye_slots_test)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(NAME mk64_render_contract COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_LIST_DIR}/render_contract.py)

add_test(NAME mk64_racer_diagnostic COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_LIST_DIR}/diagnostic_walk_test.py)
