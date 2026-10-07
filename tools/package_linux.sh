#!/usr/bin/env bash
# Stage a self-contained ARM64 package, bundling non-system shared-library dependencies.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
build_arg="${1:?build directory required}"
out_arg="${2:?output directory required}"
metadata="${3:?host source metadata file required}"
case "$build_arg" in /*) build="$build_arg" ;; *) build="$root/$build_arg" ;; esac
case "$out_arg" in /*) out="$out_arg" ;; *) out="$root/$out_arg" ;; esac
binary="$build/MarioKart64Recompiled"

case "$out" in
	"$root"/build-linux-*/package/MarioKart64Recompiled) ;;
	*) echo "refusing to replace package path outside build-linux-*/package: $out" >&2; exit 2 ;;
esac
test -x "$binary" || { echo "build executable not found: $binary" >&2; exit 1; }
test -s "$metadata" || { echo "host source metadata is missing: $metadata" >&2; exit 1; }
test -s "$build/CMakeCache.txt" || { echo "build configuration is missing: $build/CMakeCache.txt" >&2; exit 1; }

rm -rf -- "$out"
mkdir -p "$out/lib"
cp "$binary" "$out/MarioKart64Recompiled"
cp -R "$root/assets" "$out/assets"
cp "$root/recompcontrollerdb.txt" "$root/COPYING" "$out/"
cp "$root/tools/steam_frame/LAUNCH-STEAM-FRAME.sh" "$out/LAUNCH-STEAM-FRAME.sh"
if grep -q '^MK64_VR:BOOL=ON$' "$build/CMakeCache.txt"; then
	printf '%s\n' MK64FrameVR > "$out/APP-DATA-NAME"
fi
chmod +x "$out/MarioKart64Recompiled" "$out/LAUNCH-STEAM-FRAME.sh"
strip --strip-unneeded "$out/MarioKart64Recompiled"

# Resolve the full dynamic dependency closure from the original build executable. Graphics,
# display, audio, Vulkan loader and C runtime libraries remain supplied by the target OS.
queue=("$out/MarioKart64Recompiled")
while ((${#queue[@]})); do
	owner="${queue[0]}"
	queue=("${queue[@]:1}")
	while IFS= read -r library; do
		[[ -n "$library" ]] || continue
		destination="$out/lib/$library"
		[[ -e "$destination" ]] && continue
		path="$(ldd "$binary" | awk -v lib="$library" '$1 == lib && $3 ~ /^\// { print $3; exit }')"
		[[ -n "$path" && -f "$path" ]] || { echo "cannot resolve $library required by $owner" >&2; exit 1; }
		cp -L "$path" "$destination"
		queue+=("$destination")
	done < <(python3 "$root/tools/check_linux_abi.py" --list-unbundled "$owner")
done

# Package allowlist: no user game data, ROMs, saves or graphics drivers.
if find "$out" \( \
	-iname '*.z64' -o -iname '*.n64' -o -iname '*.v64' -o -iname '*.rom' \
	-o -iname '*.sav' -o -iname '*.eep' -o -iname '*.fla' -o -iname 'saves' \
	-o -iname 'libvulkan*' -o -iname '*_icd*.json' -o -iname '*.icd' \
\) -print -quit | grep -q .; then
	echo "package contains a ROM, save or graphics driver" >&2
	exit 1
fi

python3 "$root/tools/docker/write_build_metadata.py" \
	--source "$metadata" --package "$out" --build "$build"
ls -lh "$out" "$out/lib"
du -sh "$out"
