#!/usr/bin/env python3
"""Import the private ROM/patch and build the Amped Up 3D racer NRM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_model_elf import DEFAULT_CONFIG, GenerationError, generate
from importer import ImportError as ImportFailure, import_rom


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+ " + " ".join(shlex.quote(part) for part in command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def ensure_docker_image(image: str) -> None:
    inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    if inspect.returncode == 0:
        return
    run(
        [
            "docker",
            "build",
            "-t",
            image,
            "-f",
            str(ROOT / "tools" / "docker" / "linux.Dockerfile"),
            str(ROOT / "tools" / "docker"),
        ]
    )


def build_toolchain(sdk_root: Path, tool_build_dir: Path, mod_tool: Path | None, offline_tool: Path | None) -> tuple[Path, Path]:
    if mod_tool is not None and offline_tool is not None:
        return mod_tool, offline_tool

    source = sdk_root / "N64Recomp"
    if not (source / "CMakeLists.txt").is_file():
        raise ImportFailure(f"pinned N64Recomp source is missing under {sdk_root}")
    mod_tool = mod_tool or (tool_build_dir / "RecompModTool")
    offline_tool = offline_tool or (tool_build_dir / "OfflineModRecomp")

    tool_build_dir.mkdir(parents=True, exist_ok=True)
    cmake_configure = ["cmake", "-S", str(source), "-B", str(tool_build_dir), "-GNinja", "-DCMAKE_BUILD_TYPE=Release"]
    if platform.system() == "Darwin":
        # Pinned fmt 12.1.0 exposes FMT_USE_CONSTEVAL for compiler-specific
        # compatibility; disable only that feature under AppleClang 21 instead
        # of spoofing the compiler's reserved identity macro.
        cmake_configure.append("-DCMAKE_CXX_FLAGS=-DFMT_USE_CONSTEVAL=0")
    run(cmake_configure)
    run(["cmake", "--build", str(tool_build_dir), "--target", "RecompModTool", "OfflineModRecomp", "-j", str(max(2, os.cpu_count() or 2))])
    if not mod_tool.is_file() or not offline_tool.is_file():
        raise ImportFailure("pinned N64Recomp tools did not appear after the build")
    return mod_tool, offline_tool


def compile_elf(image: str) -> None:
    command = (
        "clang-15 -target mips -mips2 -mabi=32 -O2 -G0 -mno-abicalls "
        "-c build/amped_up/amped_up_model.S -o build/amped_up/amped_up_model.o && "
        "ld.lld-15 -m elf32btsmip -T tools/amped_up/model.ld "
        "--unresolved-symbols=ignore-all --emit-relocs "
        "-Map=build/amped_up/amped_up_model.map "
        "-o build/amped_up/amped_up_model.elf build/amped_up/amped_up_model.o"
    )
    run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/arm64",
            "--volume",
            f"{ROOT}:/src",
            "--workdir",
            "/src",
            image,
            "bash",
            "-lc",
            command,
        ]
    )


def parse_callback_symbols(symbol_data: bytes) -> tuple[int, list[str], list[tuple[str, int]], list[tuple[int, int]]]:
    if len(symbol_data) < 52:
        raise ImportFailure("RecompModTool produced a truncated mod symbol file")
    magic, version, *header = struct.unpack_from("<8sI10I", symbol_data)
    if magic != b"N64RSYMS" or version != 1:
        raise ImportFailure("RecompModTool produced an unsupported mod symbol file")
    (
        section_count,
        dependency_count,
        import_count,
        dependency_event_count,
        replacement_count,
        export_count,
        callback_count,
        provided_event_count,
        hook_count,
        string_size,
    ) = header

    offset = 52
    string_data = symbol_data[offset : offset + string_size]
    if len(string_data) != string_size:
        raise ImportFailure("mod symbol strings extend beyond the generated file")
    offset += string_size

    function_count = 0
    for _ in range(section_count):
        if offset + 28 > len(symbol_data):
            raise ImportFailure("mod symbol section table is truncated")
        _, _, _, _, _, section_functions, section_relocations = struct.unpack_from("<7I", symbol_data, offset)
        offset += 28
        function_count += section_functions
        offset += section_functions * 8 + section_relocations * 16
        if offset > len(symbol_data):
            raise ImportFailure("mod symbol function or relocation table is truncated")

    def get_string(start: int, length: int) -> str:
        if start + length > len(string_data):
            raise ImportFailure("mod symbol string reference extends beyond its string table")
        return string_data[start : start + length].decode("utf-8")

    dependencies: list[str] = []
    for _ in range(dependency_count):
        if offset + 12 > len(symbol_data):
            raise ImportFailure("mod symbol dependency table is truncated")
        _, start, length = struct.unpack_from("<B3xII", symbol_data, offset)
        dependencies.append(get_string(start, length))
        offset += 12
    offset += import_count * 12

    dependency_events: list[tuple[str, int]] = []
    for _ in range(dependency_event_count):
        if offset + 12 > len(symbol_data):
            raise ImportFailure("mod symbol callback event table is truncated")
        start, length, dependency_index = struct.unpack_from("<III", symbol_data, offset)
        dependency_events.append((get_string(start, length), dependency_index))
        offset += 12

    offset += replacement_count * 16 + export_count * 12
    callbacks: list[tuple[int, int]] = []
    for _ in range(callback_count):
        if offset + 8 > len(symbol_data):
            raise ImportFailure("mod symbol callback table is truncated")
        callbacks.append(struct.unpack_from("<II", symbol_data, offset))
        offset += 8
    offset += provided_event_count * 8 + hook_count * 16
    if offset != len(symbol_data):
        raise ImportFailure("mod symbol file contains unexpected trailing data")
    return function_count, dependencies, dependency_events, callbacks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True, help="private original NTSC-U .z64 ROM")
    parser.add_argument("--patch", type=Path, required=True, help="official Amped Up v3.21 .bps patch")
    parser.add_argument("--sdk-root", type=Path, default=ROOT / "lib" / "N64ModernRuntime", help="populated pinned N64ModernRuntime submodule")
    parser.add_argument("--symbols-file", type=Path, help="use a local copy of the pinned MK64 function symbols")
    parser.add_argument("--mod-tool", type=Path, help="use an already-built RecompModTool executable")
    parser.add_argument("--offline-mod-recomp", type=Path, help="use an already-built OfflineModRecomp executable")
    parser.add_argument("--tool-build-dir", type=Path, default=ROOT / "build" / "amped_up" / "n64recomp", help="native pinned SDK tool build directory")
    parser.add_argument("--docker-image", default="mariokart64recomp-frame:latest", help="local image with clang-15 and ld.lld-15")
    parser.add_argument("--output-nrm", type=Path, default=ROOT / "mods" / "amped_up.nrm",
                        help="private NRM destination; use a path outside root mods when building the application")
    parser.add_argument("--kart-source", type=Path, help="private directory with all eight supplied COLLADA kart variants and PNGs")
    args = parser.parse_args()

    output_dir = ROOT / "build" / "amped_up"
    try:
        print("Importing and verifying the supplied ROM and official BPS patch.", flush=True)
        import_report = import_rom(args.rom.resolve(), args.patch.resolve(), output_dir, DEFAULT_CONFIG)
        generated = generate(
            DEFAULT_CONFIG,
            output_dir / "amped_up_custom_segment.bin",
            output_dir / "import-report.json",
            output_dir / "amped_up_model.S",
            args.kart_source.resolve() if args.kart_source else None,
        )
        print(
            f"Prepared {generated['function_count']} unique MIPS function definitions "
            f"({generated['extracted_function_count']} extracted); direct targets: "
            f"{', '.join(generated['call_targets'])}",
            flush=True,
        )

        docker_path = shutil.which("docker")
        if docker_path is None:
            raise ImportFailure("Docker is required for the pinned MIPS clang-15/LLD build environment")
        ensure_docker_image(args.docker_image)
        compile_elf(args.docker_image)

        sdk_root = args.sdk_root.resolve()
        symbols = (args.symbols_file or (ROOT / "MarioKart64RecompSyms" / "mk64.us.syms.toml")).resolve()
        if not symbols.is_file():
            raise ImportFailure(f"pinned MK64 function symbols are missing: {symbols}")
        mod_tool, offline_tool = build_toolchain(sdk_root, args.tool_build_dir.resolve(), args.mod_tool, args.offline_mod_recomp)

        mod_dir = output_dir / "mod"
        mod_dir.mkdir(parents=True, exist_ok=True)
        template = (ROOT / "mods" / "amped_up" / "model.mod.toml").read_text(encoding="utf-8")
        build_config = output_dir / "model.mod.toml"
        template = template.replace(
            'elf_path = "../../build/amped_up/amped_up_model.elf"',
            f'elf_path = {json.dumps(str((output_dir / "amped_up_model.elf").resolve()))}',
        )
        template = template.replace(
            'func_reference_syms_file = "../../MarioKart64RecompSyms/mk64.us.syms.toml"',
            f'func_reference_syms_file = {json.dumps(str(symbols))}',
        )
        build_config.write_text(template, encoding="utf-8")
        run([str(mod_tool.resolve()), str(build_config), str(mod_dir)])
        nrm_path = mod_dir / "amped_up.nrm"
        if not nrm_path.is_file() or nrm_path.stat().st_size < 1024:
            raise ImportFailure("RecompModTool did not produce a complete Amped Up NRM")
        with zipfile.ZipFile(nrm_path) as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ImportFailure(f"generated NRM has a corrupt ZIP member: {bad_member}")
            names = set(archive.namelist())
            if not {"mod_syms.bin", "mod_binary.bin", "mod.json"}.issubset(names):
                raise ImportFailure("generated NRM is missing required recomp mod files")
            metadata = json.loads(archive.read("mod.json"))
            if metadata.get("game_id") != "mk64" or metadata.get("dependencies", []):
                raise ImportFailure("generated NRM must target MK64 without requiring a separate mod dependency")
            (
                binary_function_count,
                binary_dependencies,
                binary_dependency_events,
                binary_callbacks,
            ) = parse_callback_symbols(archive.read("mod_syms.bin"))
            expected_functions = generated["function_count"]
            if binary_function_count != expected_functions:
                raise ImportFailure(
                    f"mod symbol file contains {binary_function_count} functions; expected {expected_functions}"
                )
            if binary_dependencies != ["*"] or binary_dependency_events != [("recomp_on_init", 0)]:
                raise ImportFailure(
                    "mod symbol file does not bind recomp_on_init to the base dependency ('*')"
                )
            if len(binary_callbacks) != 1 or binary_callbacks[0] != (0, expected_functions - 1):
                raise ImportFailure("mod symbol file does not register the model-data copy callback")

        offline_c = output_dir / "offline_model_mod.c"
        run(
            [
                str(offline_tool.resolve()),
                str(mod_dir / "mod_syms.bin"),
                str(mod_dir / "mod_binary.bin"),
                str(symbols),
                str(offline_c),
            ]
        )
        offline_text = offline_c.read_text(encoding="utf-8")
        function_definitions = {
            int(index)
            for index in re.findall(
                r"^RECOMP_FUNC void mod_func_(\d+)\([^;\n]*\)[ \t]*\{",
                offline_text,
                flags=re.MULTILINE,
            )
        }
        expected_functions = generated["function_count"]
        if len(function_definitions) != expected_functions or function_definitions != set(range(expected_functions)):
            raise ImportFailure(
                f"OfflineModRecomp emitted {len(function_definitions)} unique function definitions "
                f"with indices {sorted(function_definitions)}; expected exactly {expected_functions}"
            )
        config_data = tomllib.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        stock_call_names = set(config_data["stock_calls"].values())
        missing_calls = [
            name for name in generated["call_targets"]
            if name in stock_call_names and name not in offline_text
        ]
        if missing_calls:
            raise ImportFailure("OfflineModRecomp output omitted traced call targets: " + ", ".join(missing_calls))

        package_path = args.output_nrm.resolve()
        package_path.parent.mkdir(parents=True, exist_ok=True)
        package_path.write_bytes(nrm_path.read_bytes())
        build_report = {
            "source_sha256": import_report["source_sha256"],
            "patch_sha256": import_report["patch_sha256"],
            "target_sha256": import_report["target_sha256"],
            "raw_segment_sha256": import_report["raw_segment_sha256"],
            "hydrated_segment_sha256": import_report["hydrated_segment_sha256"],
            "model_tables": import_report["model_tables"],
            "raw_racer_colour_records": import_report["raw_racer_colour_records"],
            "model_package_hydration": import_report["model_package_hydration"],
            "recompiled_custom_functions": generated["functions"],
            "visual_assets": generated["visual_assets"],
            "generated_function_definitions": generated["function_definitions"],
            "generated_function_definition_count": generated["function_count"],
            "tail_thunks": generated["tail_thunks"],
            "call_targets": generated["call_targets"],
            "manifest_game_id": metadata["game_id"],
            "manifest_dependencies": metadata.get("dependencies", []),
            "symbol_dependencies": binary_dependencies,
            "base_callback_events": [
                {"name": name, "dependency_index": dependency_index}
                for name, dependency_index in binary_dependency_events
            ],
            "registered_callbacks": [
                {"event_index": event_index, "function_index": function_index}
                for event_index, function_index in binary_callbacks
            ],
            "mod_symbol_function_count": binary_function_count,
            "offline_function_definition_count": len(function_definitions),
            "offline_function_indices": sorted(function_definitions),
            "nrm_sha256": hashlib.sha256(nrm_path.read_bytes()).hexdigest(),
            "nrm_size": nrm_path.stat().st_size,
            "private_nrm": str(package_path),
        }
        (output_dir / "model-build-report.json").write_text(json.dumps(build_report, indent=2) + "\n", encoding="utf-8")
        print(f"Built and validated {package_path} ({nrm_path.stat().st_size} bytes)", flush=True)
        print(f"Private build evidence: {output_dir / 'model-build-report.json'}", flush=True)
        return 0
    except (ImportFailure, GenerationError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"Amped Up model build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
