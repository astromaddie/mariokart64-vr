#!/usr/bin/env bash
# Build a native Linux ARM64 package for the Steam Frame.
#
#   MK64_ROM="/path/to/Mario Kart 64 (USA).z64" tools/docker/build-linux.sh [step]
#
# Steps: image, tools, recomp, build, package, abi, smoke, all (default).
# Build output stays in build-linux-aarch64/; project-configured recompiler outputs are gitignored.
set -euo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
step="${1:-all}"
image="${MK64_FRAME_IMAGE:-mariokart64recomp-frame:latest}"
build_dir="${BUILD_DIR:-build-linux-aarch64}"
jobs="${JOBS:-}"
rom="${MK64_ROM:-${ROM_FILE:-}}"

case "$build_dir" in
	/* | *..*) echo "BUILD_DIR must be a relative path inside the repository" >&2; exit 2 ;;
esac

build_image() {
	docker build --platform linux/arm64 -t "$image" -f "$repo/tools/docker/linux.Dockerfile" "$repo/tools/docker"
}

require_image() {
	if ! docker image inspect "$image" >/dev/null 2>&1; then
		echo "build container image '$image' is missing; run '$0 image' first" >&2
		exit 1
	fi
	local arch
	arch="$(docker image inspect "$image" --format '{{.Architecture}}')"
	[[ "$arch" == arm64 ]] || { echo "image '$image' has architecture $arch; linux/arm64 is required" >&2; exit 1; }
}

check_rom() {
	[[ -n "$rom" && -f "$rom" ]] || { echo "set MK64_ROM to the US Mario Kart 64 .z64 file" >&2; exit 1; }
	python3 - "$rom" <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
sha1, sha256 = hashlib.sha1(), hashlib.sha256()
with path.open("rb") as stream:
	for block in iter(lambda: stream.read(1024 * 1024), b""):
		sha1.update(block)
		sha256.update(block)
expected = (
	"579c48e211ae952530ffc8738709f078d5dd215e",
	"d6b8538dd63f0132ecb2856e7d32816ed3c30e3e479aecd23cf83fb6ba17a5da",
)
actual = (sha1.hexdigest(), sha256.hexdigest())
if actual != expected:
	sys.exit(f"{path}: ROM hashes {actual[0]} / {actual[1]} do not match the supported US ROM")
print(f"verified ROM: sha1 {actual[0]}, sha256 {actual[1]}, {path.stat().st_size} bytes")
PY
}

capture_source() {
	check_rom
	python3 "$repo/tools/docker/source_metadata.py" \
		--root "$repo" --rom "$rom" --output "$repo/$build_dir/source-metadata.json"
}

run_step() {
	local name="$1"
	shift
	local args=(docker run --rm --platform linux/arm64 -v "$repo:/src" -w /src)
	args+=(-e "BUILD_DIR=$build_dir" -e "JOBS=$jobs" -e "SOURCE_METADATA_FILE=/src/$build_dir/source-metadata.json")
	local image_id
	image_id="$(docker image inspect "$image" --format '{{.Id}}')"
	args+=(-e "MK64_FRAME_IMAGE=$image" -e "MK64_FRAME_IMAGE_ID=$image_id")
	if [[ "$name" == recomp || "$name" == smoke ]]; then
		local rom_dir="$repo/$build_dir/rom-input"
		local staged_rom="$rom_dir/mk64.us.z64"
		mkdir -p "$rom_dir"
		if [[ -L "$staged_rom" || ( -e "$staged_rom" && ! -f "$staged_rom" ) ]]; then
			echo "refusing to use non-file staged ROM path: $staged_rom" >&2
			exit 1
		elif [[ -f "$staged_rom" ]]; then
			cmp -s "$rom" "$staged_rom" || { echo "staged ROM differs from verified input: $staged_rom" >&2; exit 1; }
		else
			cp "$rom" "$staged_rom"
			chmod 0444 "$staged_rom"
		fi
		args+=(-v "$rom_dir:/rom:ro" -e ROM_FILE=/rom/mk64.us.z64)
	fi
	"${args[@]}" "$image" bash tools/docker/container-steps.sh "$name"
}

case "$step" in
	image)
		build_image
		;;
	tools)
		require_image
		run_step tools
		;;
	recomp | build | package | abi | smoke)
		require_image
		capture_source
		run_step "$step"
		;;
	all)
		check_rom
		if ! docker image inspect "$image" >/dev/null 2>&1; then
			build_image
		fi
		require_image
		capture_source
		run_step tools
		run_step recomp
		run_step build
		run_step package
		run_step abi
		run_step smoke
		;;
	*)
		echo "unknown step '$step'" >&2
		exit 2
		;;
esac
