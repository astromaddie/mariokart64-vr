#!/bin/sh
set -eu
script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
output_dir="${VR_PROBE_BUILD_DIR:-$repo_root/build-linux-aarch64/vr_probe}"
mkdir -p "$output_dir"
c++ -std=c++17 -O2 -Wall -Wextra -Wno-missing-field-initializers -Werror=return-type \
  -I/opt/openxr/include "$script_dir/probe.cpp" \
  /opt/openxr/lib/libopenxr_loader.a -Wl,--no-as-needed -lvulkan -ldl -lpthread \
  -o "$output_dir/mk64-frame-probe"
file "$output_dir/mk64-frame-probe"
sha256sum "$output_dir/mk64-frame-probe"
