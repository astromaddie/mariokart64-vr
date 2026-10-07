#!/usr/bin/env bash
# Exercise the actual launcher when Steam omits its devkit environment sidecar.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf -- "$scratch"' EXIT
package="$scratch/package with spaces"
mkdir -p "$package" "$scratch/home"
cp "$root/tools/steam_frame/LAUNCH-STEAM-FRAME.sh" "$package/"
cat > "$package/MarioKart64Recompiled" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$APP_FOLDER_PATH" > "$LAUNCH_TEST_RESULT"
[[ "$*" == '--game mk64' ]]
STUB
chmod +x "$package/"*.sh "$package/MarioKart64Recompiled"
export LAUNCH_TEST_RESULT="$scratch/result"
run() {
	env -u APP_FOLDER_PATH HOME="$scratch/home" XDG_DATA_HOME="$scratch/data" \
		"$package/LAUNCH-STEAM-FRAME.sh" --game mk64
}
run
[[ "$(cat "$LAUNCH_TEST_RESULT")" == "$scratch/data/MarioKart64Recompiled" ]]
printf '%s\n' MK64FrameVR > "$package/APP-DATA-NAME"
run
[[ "$(cat "$LAUNCH_TEST_RESULT")" == "$scratch/data/MK64FrameVR" ]]
[[ -d "$scratch/data/MK64FrameVR" ]]
env -u APP_FOLDER_PATH -u XDG_DATA_HOME HOME="$scratch/home" \
	"$package/LAUNCH-STEAM-FRAME.sh" --game mk64
[[ "$(cat "$LAUNCH_TEST_RESULT")" == "$scratch/home/.local/share/MK64FrameVR" ]]
APP_FOLDER_PATH="$scratch/custom data" "$package/LAUNCH-STEAM-FRAME.sh" --game mk64
[[ "$(cat "$LAUNCH_TEST_RESULT")" == "$scratch/custom data" ]]
printf '%s\n' '../bad-path' > "$package/APP-DATA-NAME"
if run 2> "$scratch/error"; then
	echo 'invalid package data name was accepted' >&2; exit 1
fi
grep -q 'invalid APP-DATA-NAME' "$scratch/error"
printf '%s\n' 'Launcher default, VR fallback, explicit override and invalid-name checks passed'
