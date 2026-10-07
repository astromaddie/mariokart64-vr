#!/usr/bin/env bash
# Launch from Steam so SteamVR can provide controller input to SDL.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

user_home="${HOME:?HOME must be set by Steam}"
# Steam's devkit environment sidecar is not forwarded on every normal launch.
# VR packages carry their data-folder name so the ROM, mods and VR profile are
# found even then. Explicit caller overrides still take precedence.
app_data_name="MarioKart64Recompiled"
if [[ -f "$here/APP-DATA-NAME" ]]; then
	IFS= read -r app_data_name < "$here/APP-DATA-NAME" || true
	[[ "$app_data_name" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "invalid APP-DATA-NAME" >&2; exit 2; }
fi
data="${APP_FOLDER_PATH:-${XDG_DATA_HOME:-$user_home/.local/share}/$app_data_name}"
export APP_FOLDER_PATH="$data"
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-x11}"
export DISPLAY="${DISPLAY:-:0}"
export LD_LIBRARY_PATH="$here/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mkdir -p "$APP_FOLDER_PATH"

exec ./MarioKart64Recompiled "$@"
