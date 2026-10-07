#!/bin/sh
set -eu
cd "$(dirname "$0")"
c++ -std=c++17 -O2 -Wall -Wextra -Wno-missing-field-initializers -Werror=return-type \
  -I/opt/openxr/include probe.cpp \
  /opt/openxr/lib/libopenxr_loader.a -Wl,--no-as-needed -lvulkan -ldl -lpthread \
  -o mk64-frame-probe
file mk64-frame-probe
sha256sum mk64-frame-probe
