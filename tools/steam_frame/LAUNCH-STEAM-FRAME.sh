#!/usr/bin/env bash
# Launch from Steam so SteamVR can provide controller input to SDL.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

user_home="${HOME:?HOME must be set by Steam}"
data="${APP_FOLDER_PATH:-${XDG_DATA_HOME:-$user_home/.local/share}/MarioKart64Recompiled}"
export APP_FOLDER_PATH="$data"
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-x11}"
export DISPLAY="${DISPLAY:-:0}"
export LD_LIBRARY_PATH="$here/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mkdir -p "$APP_FOLDER_PATH"

exec ./MarioKart64Recompiled "$@"
