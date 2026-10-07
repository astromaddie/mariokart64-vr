#!/usr/bin/env bash
# Steps executed inside tools/docker/linux.Dockerfile's ARM64 Ubuntu userspace.
set -euo pipefail

cd /src
arch="$(uname -m)"
[[ "$arch" == aarch64 ]] || { echo "expected aarch64 container, got $arch" >&2; exit 1; }
build="${BUILD_DIR:-build-linux-aarch64}"
jobs="${JOBS:-$(nproc)}"
type="${BUILD_TYPE:-Release}"
step="${1:?step required}"
metadata="${SOURCE_METADATA_FILE:-/src/$build/source-metadata.json}"
logs="$build/logs"
mkdir -p "$logs"
exec > >(tee "$logs/$step.log") 2>&1

flags="-fsigned-char -ffp-contract=off"

step_tools() {
	cmake -S lib/N64ModernRuntime/N64Recomp -B "$build/n64recomp" -GNinja \
		-DCMAKE_BUILD_TYPE=Release \
		-DCMAKE_C_COMPILER=clang-15 -DCMAKE_CXX_COMPILER=clang++-15
	cmake --build "$build/n64recomp" --target N64RecompCLI RSPRecomp -j "$jobs"
	test -x "$build/n64recomp/N64Recomp" -a -x "$build/n64recomp/RSPRecomp"
}

step_recomp() {
	: "${ROM_FILE:?ROM_FILE must be a read-only mount of the verified US ROM}"
	recomp="$build/n64recomp/N64Recomp"
	rsp_recomp="$build/n64recomp/RSPRecomp"
	test -x "$recomp" -a -x "$rsp_recomp" || { echo "run the tools step first" >&2; exit 1; }
	python3 - "$metadata" "$ROM_FILE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

meta = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
actual = hashlib.sha1(Path(sys.argv[2]).read_bytes()).hexdigest()
if actual != meta["rom_input"]["sha1"]:
	sys.exit("mounted ROM does not match the host-captured build input")
PY
	if [[ -e mk64.us.z64 || -L mk64.us.z64 ]]; then
		echo "refusing to replace existing mk64.us.z64; remove it only after confirming it is generated" >&2
		exit 1
	fi
	ln -s "$ROM_FILE" mk64.us.z64
	trap 'rm -f mk64.us.z64' EXIT
	"$recomp" us.toml
	"$rsp_recomp" aspMain.us.toml
	make -C patches CC=clang-15 LD=ld.lld-15 -j "$jobs"
}

step_build() {
	test -d RecompiledFuncs || { echo "run the recomp step first" >&2; exit 1; }
	cmake -S . -B "$build" -GNinja \
		-DCMAKE_BUILD_TYPE="$type" \
		-DCMAKE_C_COMPILER=clang-15 -DCMAKE_CXX_COMPILER=clang++-15 \
		-DPATCHES_C_COMPILER=clang-15 -DPATCHES_LD=ld.lld-15 \
		-DN64_RECOMP_EXECUTABLE="$build/n64recomp/N64Recomp" \
		-DCMAKE_C_FLAGS="$flags" -DCMAKE_CXX_FLAGS="$flags" \
		-DNFD_PORTAL=ON -DMK64_VR="${MK64_VR:-OFF}" \
		-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON '-DCMAKE_INSTALL_RPATH=$ORIGIN/lib'
	cmake --build "$build" --target MarioKart64Recompiled -j "$jobs"
	file "$build/MarioKart64Recompiled"
	ls -lh "$build/MarioKart64Recompiled"
}

step_package() {
	test -s "$metadata" || { echo "host source metadata is missing; rerun the host build script" >&2; exit 1; }
	tools/package_linux.sh "$build" "$build/package/MarioKart64Recompiled" "$metadata"
}

step_abi() {
	out="$build/package/MarioKart64Recompiled"
	python3 tools/check_linux_abi.py --lib-dir "$out/lib" "$out/MarioKart64Recompiled"
}

step_smoke() {
	out="$build/package/MarioKart64Recompiled"
	test -x "$out/LAUNCH-STEAM-FRAME.sh" || { echo "run package first" >&2; exit 1; }
	data="$(mktemp -d "$build/smoke.XXXXXX")"
	trap 'rm -rf "$data"' EXIT
	mkdir -p "$data/home"
	if [[ -n "${ROM_FILE:-}" ]]; then
		cp "$ROM_FILE" "$data/mk64.us.z64"
	fi
	ulimit -c 0
	set +e
	xvfb-run -a -s '-screen 0 1280x720x24' \
		env HOME="$data/home" APP_FOLDER_PATH="$data" SDL_AUDIODRIVER=dummy \
		SDL_VIDEODRIVER=x11 timeout --kill-after=5s "${SMOKE_SECONDS:-30}s" "$out/LAUNCH-STEAM-FRAME.sh"
	status=$?
	set -e
	echo "smoke exit status $status (124 means the app stayed open until timeout)"
	if [[ "$status" != 0 && "$status" != 124 ]]; then
		echo "host UI smoke failed; see $logs/smoke.log" >&2
		return "$status"
	fi
	if [[ -n "${ROM_FILE:-}" ]]; then
		test -s "$data/mk64.us.z64"
	fi
}

"step_$step"
