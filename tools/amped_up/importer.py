#!/usr/bin/env python3
"""Validate private retail inputs and hydrate Amped Up's 3D racer packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import tomllib
import zlib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "mods" / "amped_up" / "models.toml"


class ImportError(ValueError):
    """Raised when an input is not the pinned ROM or official BPS patch."""


@dataclass(frozen=True)
class PatchResult:
    target: bytes
    source_crc32: int
    target_crc32: int
    patch_crc32: int


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bps_number(data: bytes, position: int, end: int) -> tuple[int, int]:
    """Read BPS's biased base-128 integer, rejecting truncated or oversized input."""
    value = 0
    shift = 1
    while position < end:
        byte = data[position]
        position += 1
        value += (byte & 0x7F) * shift
        if byte & 0x80:
            if value > 0xFFFFFFFF:
                raise ImportError("BPS integer exceeds the supported 32-bit range")
            return value, position
        shift <<= 7
        value += shift
        if shift > 0x100000000:
            raise ImportError("BPS integer is too large")
    raise ImportError("truncated BPS integer")


def read_bps_signed(data: bytes, position: int, end: int) -> tuple[int, int]:
    encoded, position = read_bps_number(data, position, end)
    magnitude = encoded >> 1
    return (-magnitude if encoded & 1 else magnitude), position


def apply_bps(source: bytes, patch: bytes) -> PatchResult:
    """Apply a BPS1 patch and validate its source, target, and patch CRCs."""
    if len(patch) < 16 or patch[:4] != b"BPS1":
        raise ImportError("input is not a complete BPS1 patch")

    patch_end = len(patch) - 12
    position = 4
    source_size, position = read_bps_number(patch, position, patch_end)
    target_size, position = read_bps_number(patch, position, patch_end)
    metadata_size, position = read_bps_number(patch, position, patch_end)
    if source_size != len(source):
        raise ImportError(f"BPS expects {source_size} source bytes, received {len(source)}")
    if metadata_size > patch_end - position:
        raise ImportError("BPS metadata extends beyond the patch commands")
    position += metadata_size

    output = bytearray()
    source_relative = 0
    target_relative = 0

    while position < patch_end:
        action, position = read_bps_number(patch, position, patch_end)
        length = (action >> 2) + 1
        mode = action & 3
        if length > target_size - len(output):
            raise ImportError("BPS action writes beyond the declared target size")

        if mode == 0:  # SourceRead
            start = len(output)
            end = start + length
            if end > len(source):
                raise ImportError("BPS SourceRead extends beyond the source ROM")
            output.extend(source[start:end])
        elif mode == 1:  # TargetRead
            end = position + length
            if end > patch_end:
                raise ImportError("truncated BPS TargetRead action")
            output.extend(patch[position:end])
            position = end
        elif mode == 2:  # SourceCopy
            delta, position = read_bps_signed(patch, position, patch_end)
            source_relative += delta
            end = source_relative + length
            if source_relative < 0 or end > len(source):
                raise ImportError("BPS SourceCopy points outside the source ROM")
            output.extend(source[source_relative:end])
            source_relative = end
        else:  # TargetCopy, with the overlap behavior required by BPS1.
            delta, position = read_bps_signed(patch, position, patch_end)
            target_relative += delta
            if target_relative < 0 or target_relative >= len(output):
                raise ImportError("BPS TargetCopy points outside already-produced target data")
            for _ in range(length):
                if target_relative >= len(output):
                    raise ImportError("BPS TargetCopy reads beyond produced target data")
                output.append(output[target_relative])
                target_relative += 1

    if position != patch_end:
        raise ImportError("BPS command stream does not end at its checksum footer")
    if len(output) != target_size:
        raise ImportError(f"BPS produced {len(output)} bytes; expected {target_size}")

    expected_source_crc, expected_target_crc, expected_patch_crc = struct.unpack_from("<III", patch, patch_end)
    source_crc = zlib.crc32(source) & 0xFFFFFFFF
    target_crc = zlib.crc32(output) & 0xFFFFFFFF
    patch_crc = zlib.crc32(patch[:-4]) & 0xFFFFFFFF
    if source_crc != expected_source_crc:
        raise ImportError(f"BPS source CRC mismatch: {source_crc:08x} != {expected_source_crc:08x}")
    if target_crc != expected_target_crc:
        raise ImportError(f"BPS target CRC mismatch: {target_crc:08x} != {expected_target_crc:08x}")
    if patch_crc != expected_patch_crc:
        raise ImportError(f"BPS patch CRC mismatch: {patch_crc:08x} != {expected_patch_crc:08x}")

    return PatchResult(output, source_crc, target_crc, patch_crc)


def load_config(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ImportError(f"cannot read importer config {path}: {exc}") from exc


def read_expected_inputs(source_path: Path, patch_path: Path, config: dict) -> tuple[bytes, bytes, PatchResult]:
    try:
        source = source_path.read_bytes()
        patch = patch_path.read_bytes()
    except OSError as exc:
        raise ImportError(f"cannot read source ROM or BPS patch: {exc}") from exc

    rom_expect = config["rom"]
    if sha256(source) != rom_expect["source_sha256"]:
        raise ImportError("source ROM SHA-256 does not match the configured retail ROM")
    if sha256(patch) != rom_expect["patch_sha256"]:
        raise ImportError("BPS SHA-256 does not match the official Amped Up v3.21 patch")

    result = apply_bps(source, patch)
    if result.source_crc32 != int(rom_expect["source_crc32"], 16):
        raise ImportError("source ROM CRC does not match the configured retail ROM")
    if result.target_crc32 != int(rom_expect["target_crc32"], 16):
        raise ImportError("patched ROM CRC does not match the configured Amped Up target")
    if sha256(result.target) != rom_expect["target_sha256"]:
        raise ImportError("patched ROM SHA-256 does not match the configured Amped Up target")
    return source, patch, result


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    try:
        with temporary.open("wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_segment_layout(segment_config: dict, retail_memory: dict, target_size: int) -> tuple[int, int, int]:
    rom_start = int(segment_config["rom_start"], 16)
    ram_start = int(segment_config["ram_start"], 16)
    length = int(segment_config["length"], 16)
    heap_end = int(retail_memory["heap_pool_end"], 16)
    static_end = int(retail_memory["static_noload_end"], 16)
    expansion_end = int(retail_memory["expansion_ram_end"], 16)

    if length <= 0 or length % 4 or ram_start % 4:
        raise ImportError("custom segment must have a positive, word-aligned fixed-address range")
    if rom_start + length > target_size:
        raise ImportError("configured custom segment extends beyond the patched ROM")
    if ram_start < max(heap_end, static_end):
        raise ImportError("custom segment overlaps original retail heap or static memory")
    if ram_start + length > expansion_end:
        raise ImportError("custom segment extends beyond the configured 8 MiB expansion RAM")
    return rom_start, ram_start, length


def _configured_int(value: str | int, name: str) -> int:
    try:
        return int(value, 16) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as exc:
        raise ImportError(f"invalid hexadecimal value for {name}: {value!r}") from exc


def _segment_virtual_address(address: int, segment_ram_start: int, segment_size: int, context: str) -> int:
    """Resolve a segment-0 token or KSEG0 pointer into this fixed RAM image."""
    if 0 <= address <= 0x00FFFFFF:
        virtual = 0x80000000 | address
    elif address & 0xFF000000 == 0x80000000:
        virtual = address
    else:
        raise ImportError(f"{context} is not a segment-0/KSEG0 pointer: 0x{address:08X}")
    if not segment_ram_start <= virtual < segment_ram_start + segment_size:
        raise ImportError(f"{context} points outside the copied custom segment: 0x{address:08X}")
    return virtual


def _segment_offset(address: int, segment_ram_start: int, segment_size: int, context: str) -> int:
    return _segment_virtual_address(address, segment_ram_start, segment_size, context) - segment_ram_start


def _normalize_segment_pointer(
    hydrated: bytearray,
    pointer_location: int,
    segment_ram_start: int,
    segment_size: int,
    context: str,
    *,
    allow_null: bool = True,
) -> int | None:
    """Rewrite one typed CPU pointer as its canonical 24-bit segment-0 offset."""
    location = _segment_offset(pointer_location, segment_ram_start, segment_size, f"{context} field")
    value = struct.unpack_from(">I", hydrated, location)[0]
    if value == 0:
        if allow_null:
            return None
        raise ImportError(f"{context} is null")
    virtual = _segment_virtual_address(value, segment_ram_start, segment_size, context)
    struct.pack_into(">I", hydrated, location, virtual & 0x00FFFFFF)
    return virtual


def hydrate_model_packages(
    target: bytes,
    raw_segment: bytes,
    segment_ram_start: int,
    package_table: dict,
    package_configs: list[dict],
    cpu_pointer_tables: list[dict] | None = None,
    cpu_pointer_roots: list[dict] | None = None,
    code_patches: list[dict] | None = None,
    static_display_list_tables: list[dict] | None = None,
    emitted_display_list_roots: list[dict] | None = None,
    emitted_display_list_ranges: list[dict] | None = None,
    item_display_list_roots: list[dict] | None = None,
) -> tuple[bytes, dict]:
    """Copy the eight checked selected model packages and resolve their live GBI pointers.

    The original loader copies each selected VROM range to its fixed RAM root and
    rebases G_DL/G_SETTIMG words in that range. Its G_VTX words remain untouched,
    so package-local vertex references need an additional, bounded relocation.
    """
    if len(package_configs) != 8:
        raise ImportError(f"expected eight high-detail racer model packages, found {len(package_configs)}")

    table_address = _configured_int(package_table["ram_address"], "model package table address")
    row_stride = int(package_table["row_stride"])
    rows_per_character = int(package_table["rows_per_character"])
    expected_marker = _configured_int(package_table["expected_marker"], "model package row marker")
    selected_slot = int(package_table.get("selected_slot", 0))
    entry_stride = int(package_table.get("entry_stride", 16))
    if entry_stride != 16:
        raise ImportError("model selectors must use the traced G_DL/ENDDL 16-byte stride")
    if row_stride != 16 or rows_per_character <= 0 or not 0 <= selected_slot < rows_per_character:
        raise ImportError("model package table must use the traced 16-byte rows and a positive character stride")
    table_offset = table_address - segment_ram_start
    if table_offset < 0 or table_offset + max(p["row_index"] for p in package_configs) * row_stride + 16 > len(raw_segment):
        raise ImportError("model package row table falls outside the copied custom segment")

    packages = []
    seen_names: set[str] = set()
    seen_rows: set[int] = set()
    for configured in package_configs:
        try:
            name = str(configured["name"])
            row_index = int(configured["row_index"])
            ram_start = _configured_int(configured["ram_address"], f"{name} RAM address")
            rom_start = _configured_int(configured["rom_start"], f"{name} ROM start")
            rom_end = _configured_int(configured["rom_end"], f"{name} ROM end")
            entry_count = int(configured["entry_count"])
            geometry_root_offset = _configured_int(configured["geometry_root_offset"], f"{name} geometry root offset")
        except (KeyError, TypeError, ValueError) as exc:
            raise ImportError(f"invalid model package configuration: {exc}") from exc

        if not name or name in seen_names:
            raise ImportError(f"model package names must be unique and nonempty: {name!r}")
        if row_index in seen_rows or row_index < 0 or row_index % rows_per_character != selected_slot:
            raise ImportError(f"model package {name} has an invalid or duplicate selected row index {row_index}")
        if ram_start % 8 or rom_start % 8 or rom_end % 8 or rom_end <= rom_start:
            raise ImportError(f"model package {name} has an invalid or unaligned source or destination range")
        package_size = rom_end - rom_start
        if rom_end > len(target):
            raise ImportError(f"model package {name} extends beyond the patched ROM")
        if ram_start < segment_ram_start or ram_start + package_size > segment_ram_start + len(raw_segment):
            raise ImportError(f"model package {name} destination is outside the copied custom segment")
        if entry_count <= 0 or entry_count * entry_stride > package_size:
            raise ImportError(f"model package {name} has an invalid display-list entry table")
        if geometry_root_offset % 8 or geometry_root_offset < entry_count * entry_stride or geometry_root_offset + 8 > package_size:
            raise ImportError(f"model package {name} has an invalid geometry-root offset")

        row_offset = table_offset + row_index * row_stride
        row_marker, row_ram, row_rom_start, row_rom_end = struct.unpack_from(">4I", raw_segment, row_offset)
        if (row_marker, row_ram, row_rom_start, row_rom_end) != (expected_marker, ram_start, rom_start, rom_end):
            raise ImportError(
                f"model package {name} does not match its stock selected row at index {row_index}: "
                f"{row_marker:08X}/{row_ram:08X}/{row_rom_start:08X}/{row_rom_end:08X}"
            )

        destination_offset = ram_start - segment_ram_start
        if any(raw_segment[destination_offset : destination_offset + package_size]):
            raise ImportError(f"model package {name} destination is not an unused zero-filled segment range")

        package = {
            "name": name,
            "row_index": row_index,
            "ram_start": ram_start,
            "rom_start": rom_start,
            "rom_end": rom_end,
            "size": package_size,
            "destination_offset": destination_offset,
            "entry_count": entry_count,
            "geometry_root_offset": geometry_root_offset,
        }
        packages.append(package)
        seen_names.add(name)
        seen_rows.add(row_index)

    for range_key, start_key, end_key, label in (
        ("rom_start", "rom_start", "rom_end", "VROM"),
        ("ram_start", "ram_start", "ram_start", "RAM"),
    ):
        ordered = sorted(packages, key=lambda package: package[range_key])
        for previous, current in zip(ordered, ordered[1:]):
            previous_end = previous[end_key] if label == "VROM" else previous["ram_start"] + previous["size"]
            if current[start_key] < previous_end:
                raise ImportError(f"model package {previous['name']} overlaps {current['name']} in {label}")
    expected_rows = list(range(selected_slot, len(package_configs) * rows_per_character, rows_per_character))
    if sorted(seen_rows) != expected_rows:
        raise ImportError(f"model packages must cover all eight selected rows in order: {expected_rows}")

    hydrated = bytearray(raw_segment)
    stock_relocations = {"g_dl": 0, "g_settimg": 0}
    for package in packages:
        source = target[package["rom_start"] : package["rom_end"]]
        start = package["rom_start"]
        end = package["rom_end"]
        destination_offset = package["destination_offset"]
        hydrated[destination_offset : destination_offset + package["size"]] = source

        # Match the original DMA helper: visit every 8-byte record in the copied
        # range, and relocate only opcodes 0x06 and 0xFD whose word 1 is local.
        for offset in range(0, len(source), 8):
            w0, w1 = struct.unpack_from(">II", source, offset)
            opcode = w0 >> 24
            if opcode in (0x06, 0xFD) and start <= w1 < end:
                translated = package["ram_start"] + (w1 - start)
                struct.pack_into(">I", hydrated, destination_offset + offset + 4, translated)
                stock_relocations["g_dl" if opcode == 0x06 else "g_settimg"] += 1

    applied_code_patches = []
    seen_patch_addresses: set[int] = set()
    for configured in code_patches or []:
        address = _configured_int(configured["address"], "code patch address")
        expected = _configured_int(configured["expected_word"], f"{configured.get('purpose', 'code patch')} expected word")
        replacement = _configured_int(
            configured["replacement_word"], f"{configured.get('purpose', 'code patch')} replacement word"
        )
        if address % 4 or address in seen_patch_addresses:
            raise ImportError(f"code patch has an unaligned or duplicate address 0x{address:08X}")
        offset = _segment_offset(address, segment_ram_start, len(hydrated), "code patch")
        actual = struct.unpack_from(">I", hydrated, offset)[0]
        if actual != expected:
            raise ImportError(
                f"code patch at 0x{address:08X} expected 0x{expected:08X}, found 0x{actual:08X}"
            )
        struct.pack_into(">I", hydrated, offset, replacement)
        applied_code_patches.append(
            {"address": f"0x{address:08X}", "from": f"0x{expected:08X}", "to": f"0x{replacement:08X}",
             "purpose": configured.get("purpose", "")}
        )
        seen_patch_addresses.add(address)

    normalized_tables = []
    armature_roots: list[tuple[str, int]] = []
    animation_roots: list[tuple[str, int]] = []
    for table in cpu_pointer_tables or []:
        table_name = str(table.get("name", "unnamed"))
        table_address = _configured_int(table["ram_address"], f"{table_name} pointer table address")
        entries = int(table["entries"])
        kind = str(table["kind"])
        if entries <= 0 or kind not in ("armature", "animation"):
            raise ImportError(f"CPU pointer table {table_name} has invalid entries or kind")
        table_offset = _segment_offset(
            table_address, segment_ram_start, len(hydrated), f"CPU pointer table {table_name}"
        )
        if table_offset + entries * 4 > len(hydrated):
            raise ImportError(f"CPU pointer table {table_name} extends beyond the copied custom segment")
        pointers = []
        for index in range(entries):
            location = table_address + index * 4
            pointer = _normalize_segment_pointer(
                hydrated, location, segment_ram_start, len(hydrated),
                f"CPU pointer table {table_name}[{index}]", allow_null=False,
            )
            assert pointer is not None
            pointers.append(pointer)
            (armature_roots if kind == "armature" else animation_roots).append(
                (f"{table_name}[{index}]", pointer)
            )
        normalized_tables.append(
            {"name": table_name, "kind": kind, "ram_address": f"0x{table_address:08X}",
             "entries": entries, "normalized_pointers": [f"0x{x & 0x00FFFFFF:06X}" for x in pointers]}
        )

    for configured in cpu_pointer_roots or []:
        name = str(configured.get("name", "unnamed"))
        address = _configured_int(configured["ram_address"], f"{name} CPU pointer root")
        kind = str(configured["kind"])
        if kind not in ("armature", "animation"):
            raise ImportError(f"CPU pointer root {name} has unsupported kind {kind!r}")
        _segment_offset(address, segment_ram_start, len(hydrated), f"CPU pointer root {name}")
        (armature_roots if kind == "armature" else animation_roots).append((name, address))

    animation_addresses: set[int] = set()
    for name, address in animation_roots:
        if address in animation_addresses:
            continue
        offset = _segment_offset(address, segment_ram_start, len(hydrated), f"Animation {name}")
        if offset + 20 > len(hydrated):
            raise ImportError(f"Animation {name} structure extends beyond the copied custom segment")
        for field_offset, field_name in ((12, "angle_array"), (16, "animation_cycle_spec_vector")):
            _normalize_segment_pointer(
                hydrated, address + field_offset, segment_ram_start, len(hydrated),
                f"Animation {name}.{field_name}", allow_null=False,
            )
        animation_addresses.add(address)

    model_display_list_roots: list[dict] = []
    armature_addresses: set[int] = set()
    for name, root in armature_roots:
        if root in armature_addresses:
            continue
        address = root
        for limb_index in range(4096):
            offset = _segment_offset(address, segment_ram_start, len(hydrated), f"Armature {name} limb {limb_index}")
            if offset + 8 > len(hydrated):
                raise ImportError(f"Armature {name} has no stop record before the custom segment ends")
            record_type, size_words = struct.unpack_from(">II", hydrated, offset)
            if record_type not in (0, 1, 2, 3) or size_words < 2:
                raise ImportError(
                    f"Armature {name} has an invalid record type/size at 0x{address:08X}: "
                    f"{record_type}/{size_words}"
                )
            record_size = size_words * 4
            if offset + record_size > len(hydrated):
                raise ImportError(f"Armature {name} record at 0x{address:08X} exceeds the copied custom segment")
            if record_type == 0:
                if size_words < 4:
                    raise ImportError(f"Armature {name} model record is shorter than its model pointer")
                model = _normalize_segment_pointer(
                    hydrated, address + 12, segment_ram_start, len(hydrated),
                    f"Armature {name} limb {limb_index}.model",
                )
                if model is not None:
                    model_display_list_roots.append(
                        {"name": f"{name}.limb_{limb_index}", "address": model}
                    )
            address += record_size
            if record_type == 3:
                break
        else:
            raise ImportError(f"Armature {name} exceeds the 4096-record traversal limit")
        armature_addresses.add(root)

    def package_for_rom_address(address: int) -> dict | None:
        return next((package for package in packages if package["rom_start"] <= address < package["rom_end"]), None)

    segment_end = segment_ram_start + len(hydrated)
    package_for_ram_address = lambda address: next(
        (package for package in packages if package["ram_start"] <= address < package["ram_start"] + package["size"]),
        None,
    )
    unique_display_lists: set[int] = set()
    unique_commands: set[int] = set()
    unique_vertex_commands: set[int] = set()
    unique_local_vertex_commands: set[int] = set()
    unique_fixed_vertex_commands: set[int] = set()
    unique_texture_commands: set[int] = set()
    unique_branch_z_commands: set[int] = set()
    normalized_gbi_addresses: dict[str, set[int]] = {
        "g_dl": set(), "g_vtx": set(), "g_settimg": set(), "g_branch_z": set()
    }

    def resolve_gbi_address(address: int, context: str) -> tuple[int, dict | None]:
        source_package = package_for_rom_address(address)
        if source_package is not None:
            virtual = source_package["ram_start"] + (address - source_package["rom_start"])
        else:
            virtual = _segment_virtual_address(address, segment_ram_start, len(hydrated), context)
        if not segment_ram_start <= virtual < segment_end:
            raise ImportError(f"{context} points outside initialized custom-segment bytes: 0x{address:08X}")
        return virtual, source_package

    def inspect_graph(roots: list[int], name: str) -> dict:
        visited: set[tuple[int, tuple[int, int] | None]] = set()
        active: set[tuple[int, tuple[int, int] | None]] = set()
        metrics = {"display_lists": 0, "commands": 0, "g_vtx": 0, "g_vtx_local_relocations": 0,
                   "g_vtx_fixed_segment": 0, "g_settimg": 0, "g_settimg_pointers": [],
                   "g_branch_z": 0, "g_branch_z_targets": [], "triangles": 0}
        end_half1: dict[tuple[int, tuple[int, int] | None], tuple[int, int] | None] = {}

        def walk(address: int, depth: int = 0, incoming_half1: tuple[int, int] | None = None) -> tuple[int, int] | None:
            address = _segment_virtual_address(address, segment_ram_start, len(hydrated), f"{name} display-list root")
            if depth > 256:
                raise ImportError(f"model package {name} display-list nesting exceeds 256 levels")
            if address < segment_ram_start or address + 8 > segment_end or address % 8:
                raise ImportError(f"model package {name} has an out-of-range or unaligned G_DL target 0x{address:08X}")
            state = (address, incoming_half1)
            if state in active:
                raise ImportError(f"model package {name} has a cyclic G_DL reference at 0x{address:08X}")
            if state in visited:
                return end_half1[state]

            package = package_for_ram_address(address)
            list_end = package["ram_start"] + package["size"] if package else segment_end
            active.add(state)
            visited.add(state)
            unique_display_lists.add(address)
            metrics["display_lists"] += 1
            cursor = address
            current_half1 = incoming_half1
            for _ in range(8192):
                if cursor + 8 > list_end:
                    raise ImportError(f"model package {name} display list at 0x{address:08X} is unterminated or crosses its data range")
                offset = cursor - segment_ram_start
                w0, w1 = struct.unpack_from(">II", hydrated, offset)
                opcode = w0 >> 24
                metrics["commands"] += 1
                unique_commands.add(cursor)

                if opcode in (0xBF, 0xB1):
                    metrics["triangles"] += 1 if opcode == 0xBF else 2
                if opcode == 0x04:  # F3DEX G_VTX: n = bits 10..15, sizeof(Vtx) = 16.
                    unique_vertex_commands.add(cursor)
                    vertex_count = (w0 >> 10) & 0x3F
                    vertex_bytes = vertex_count * 16
                    if vertex_count == 0:
                        raise ImportError(f"model package {name} has a zero-count G_VTX at 0x{cursor:08X}")
                    vertex_address, source_package = resolve_gbi_address(
                        w1, f"model package {name} G_VTX at 0x{cursor:08X}"
                    )
                    if vertex_address % 8:
                        raise ImportError(
                            f"model package {name} has an unaligned G_VTX pointer 0x{w1:08X} "
                            f"at 0x{cursor:08X}"
                        )
                    if source_package is not None:
                        if w1 + vertex_bytes > source_package["rom_end"]:
                            raise ImportError(
                                f"model package {name} G_VTX at 0x{cursor:08X} crosses source package "
                                f"{source_package['name']} at 0x{w1:08X}"
                            )
                        if vertex_address + vertex_bytes > source_package["ram_start"] + source_package["size"]:
                            raise ImportError(
                                f"model package {name} G_VTX at 0x{cursor:08X} crosses destination package "
                                f"{source_package['name']} at 0x{vertex_address:08X}"
                            )
                        if cursor not in unique_fixed_vertex_commands:
                            unique_local_vertex_commands.add(cursor)
                        metrics["g_vtx_local_relocations"] += 1
                    else:
                        if cursor not in unique_local_vertex_commands:
                            unique_fixed_vertex_commands.add(cursor)
                        metrics["g_vtx_fixed_segment"] += 1
                    if vertex_address + vertex_bytes > segment_end:
                        raise ImportError(
                            f"model package {name} G_VTX at 0x{cursor:08X} points outside initialized bytes "
                            f"at 0x{vertex_address:08X} ({vertex_bytes} bytes)"
                        )
                    target_package = package_for_ram_address(vertex_address)
                    if target_package and vertex_address + vertex_bytes > target_package["ram_start"] + target_package["size"]:
                        raise ImportError(
                            f"model package {name} G_VTX at 0x{cursor:08X} crosses destination package "
                            f"{target_package['name']} at 0x{vertex_address:08X}"
                        )
                    struct.pack_into(">I", hydrated, offset + 4, vertex_address & 0x00FFFFFF)
                    normalized_gbi_addresses["g_vtx"].add(cursor)
                    metrics["g_vtx"] += 1
                elif opcode == 0x06:  # G_DL
                    display_list_address, _ = resolve_gbi_address(
                        w1, f"model package {name} G_DL at 0x{cursor:08X}"
                    )
                    struct.pack_into(">I", hydrated, offset + 4, display_list_address & 0x00FFFFFF)
                    normalized_gbi_addresses["g_dl"].add(cursor)
                    current_half1 = walk(display_list_address, depth + 1, current_half1)
                elif opcode == 0xFD:  # G_SETTIMG
                    image_address, _ = resolve_gbi_address(
                        w1, f"model package {name} G_SETTIMG at 0x{cursor:08X}"
                    )
                    struct.pack_into(">I", hydrated, offset + 4, image_address & 0x00FFFFFF)
                    normalized_gbi_addresses["g_settimg"].add(cursor)
                    metrics["g_settimg"] += 1
                    unique_texture_commands.add(cursor)
                    metrics["g_settimg_pointers"].append(f"0x{image_address & 0x00FFFFFF:06X}")
                elif opcode == 0xB4:  # F3DEX G_RDPHALF_1; G_BRANCH_Z consumes this pointer.
                    current_half1 = (w1, cursor)
                elif opcode == 0xB0:  # F3DEX G_BRANCH_Z; trace the taken path as well as fallthrough.
                    if current_half1 is None:
                        raise ImportError(
                            f"model package {name} has a G_BRANCH_Z without a preceding G_RDPHALF_1 "
                            f"at 0x{cursor:08X}"
                        )
                    branch_value, half1_command = current_half1
                    branch_address, _ = resolve_gbi_address(
                        branch_value, f"model package {name} G_BRANCH_Z at 0x{cursor:08X}"
                    )
                    struct.pack_into(">I", hydrated, half1_command - segment_ram_start + 4,
                                     branch_address & 0x00FFFFFF)
                    normalized_gbi_addresses["g_branch_z"].add(half1_command)
                    unique_branch_z_commands.add(cursor)
                    metrics["g_branch_z"] += 1
                    metrics["g_branch_z_targets"].append(f"0x{branch_address & 0x00FFFFFF:06X}")
                    walk(branch_address, depth + 1, (branch_address & 0x00FFFFFF, half1_command))

                if opcode == 0xB8:  # F3DEX G_ENDDL
                    active.remove(state)
                    end_half1[state] = current_half1
                    return current_half1
                cursor += 8

            raise ImportError(f"model package {name} display list at 0x{address:08X} exceeds the 8192-command bound")

        for root in roots:
            walk(root)
        return metrics

    package_reports = []
    all_texture_pointers: set[str] = set()
    for package in packages:
        roots = [package["ram_start"] + index * entry_stride for index in range(package["entry_count"])]
        geometry_root = package["ram_start"] + package["geometry_root_offset"]
        metrics = inspect_graph(roots + [geometry_root], package["name"])
        if metrics["g_vtx"] == 0:
            raise ImportError(f"model package {package['name']} has no reachable vertex geometry")
        nonempty_entries = sum(
            struct.unpack_from(">I", hydrated, root - segment_ram_start)[0] >> 24 != 0xB8
            for root in roots
        )
        if nonempty_entries == 0:
            raise ImportError(f"model package {package['name']} has no nonempty display-list entry")
        package_reports.append(
            {
                "name": package["name"],
                "row_index": package["row_index"],
                "row_marker": f"0x{expected_marker:08X}",
                "ram_address": f"0x{package['ram_start']:08X}",
                "rom_start": f"0x{package['rom_start']:08X}",
                "rom_end": f"0x{package['rom_end']:08X}",
                "size": f"0x{package['size']:X}",
                "display_list_entries": package["entry_count"],
                "nonempty_display_list_entries": nonempty_entries,
                "geometry_root": f"0x{geometry_root:08X}",
                "reachable_display_lists": metrics["display_lists"],
                "reachable_commands": metrics["commands"],
                "reachable_g_vtx": metrics["g_vtx"],
                "g_vtx_local_relocations": metrics["g_vtx_local_relocations"],
                "g_vtx_fixed_segment_references": metrics["g_vtx_fixed_segment"],
                "reachable_g_settimg": metrics["g_settimg"],
                "g_settimg_pointers": sorted(set(metrics["g_settimg_pointers"])),
            }
        )
        all_texture_pointers.update(metrics["g_settimg_pointers"])

    model_roots_by_address: dict[int, list[str]] = {}
    for model_root in model_display_list_roots:
        model_roots_by_address.setdefault(model_root["address"], []).append(model_root["name"])
    external_model_roots = [
        {"name": ",".join(names), "address": address}
        for address, names in sorted(model_roots_by_address.items())
        if package_for_ram_address(address) is None
    ]
    external_model_metrics = inspect_graph(
        [root["address"] for root in external_model_roots], "armature-model-roots"
    ) if external_model_roots else {
        "display_lists": 0, "commands": 0, "g_vtx": 0, "g_vtx_local_relocations": 0,
        "g_vtx_fixed_segment": 0, "g_settimg": 0, "g_settimg_pointers": [],
        "g_branch_z": 0, "g_branch_z_targets": [],
    }
    all_texture_pointers.update(external_model_metrics["g_settimg_pointers"])

    static_tables = static_display_list_tables or []
    if len(static_tables) != 4:
        raise ImportError(f"expected the four traced static display-list tables, found {len(static_tables)}")
    static_table_reports = []
    seen_static_names: set[str] = set()
    seen_static_ranges: list[tuple[int, int, str]] = []
    for configured in static_tables:
        name = str(configured.get("name", ""))
        address = _configured_int(configured["ram_address"], f"{name} static display-list table address")
        entries = int(configured["entries"])
        expected = [_configured_int(pointer, f"{name} expected root") for pointer in configured["expected_pointers"]]
        if not name or name in seen_static_names or entries != 8 or len(expected) != entries:
            raise ImportError(f"static display-list table {name!r} must be unique and contain eight checked roots")
        table_offset = _segment_offset(address, segment_ram_start, len(hydrated), f"static display-list table {name}")
        table_end = address + entries * 4
        if address % 4 or table_end > segment_end:
            raise ImportError(f"static display-list table {name} is unaligned or extends beyond the custom segment")
        for prior_start, prior_end, prior_name in seen_static_ranges:
            if address < prior_end and prior_start < table_end:
                raise ImportError(f"static display-list table {name} overlaps {prior_name}")
        pointers = list(struct.unpack_from(">" + "I" * entries, hydrated, table_offset))
        if pointers != expected:
            raise ImportError(
                f"static display-list table {name} does not match its pinned renderer roots: "
                f"{[f'0x{x:08X}' for x in pointers]}"
            )
        roots = []
        for index, pointer in enumerate(pointers):
            root = _segment_virtual_address(
                pointer, segment_ram_start, len(hydrated), f"static display-list table {name}[{index}]"
            )
            if root % 8:
                raise ImportError(f"static display-list table {name}[{index}] is not 8-byte aligned")
            roots.append(root)
        metrics = inspect_graph(roots, name)
        all_texture_pointers.update(metrics["g_settimg_pointers"])
        static_table_reports.append({
            "name": name,
            "ram_address": f"0x{address:08X}",
            "entries": entries,
            "roots": [f"0x{x & 0x00FFFFFF:06X}" for x in roots],
            "reachable_display_lists": metrics["display_lists"],
            "reachable_commands": metrics["commands"],
            "reachable_g_vtx": metrics["g_vtx"],
            "reachable_g_settimg": metrics["g_settimg"],
            "reachable_g_branch_z": metrics["g_branch_z"],
            "g_branch_z_targets": sorted(set(metrics["g_branch_z_targets"])),
        })
        seen_static_names.add(name)
        seen_static_ranges.append((address, table_end, name))

    item_reports = []
    for configured in item_display_list_roots or []:
        address = _configured_int(configured["ram_address"], "item model root")
        metrics = inspect_graph([address], configured["name"])
        if metrics["triangles"] != configured["triangles"]:
            raise ImportError(f"item root {configured['name']} triangle count changed")
        item_reports.append({"name": configured["name"], "address": f"0x{address:08X}", **metrics})
        all_texture_pointers.update(metrics["g_settimg_pointers"])

    emitted_roots = emitted_display_list_roots or []
    if len(emitted_roots) != 8:
        raise ImportError(f"expected the eight traced renderer-emitted display-list roots, found {len(emitted_roots)}")
    emitted_root_reports = []
    seen_emitted_names: set[str] = set()
    seen_emitted_addresses: set[int] = set()
    for configured in emitted_roots:
        name = str(configured.get("name", ""))
        address = _configured_int(configured["ram_address"], f"{name} emitted display-list root")
        geometry = configured.get("geometry")
        if not name or name in seen_emitted_names or not isinstance(geometry, bool):
            raise ImportError(f"emitted display-list root {name!r} needs a unique name and geometry classification")
        _segment_offset(address, segment_ram_start, len(hydrated), f"emitted display-list root {name}")
        if address % 8 or address in seen_emitted_addresses:
            raise ImportError(f"emitted display-list root {name} is unaligned or duplicated")
        metrics = inspect_graph([address], name)
        if geometry and metrics["g_vtx"] == 0:
            raise ImportError(f"emitted geometry root {name} has no reachable G_VTX commands")
        if not geometry and (metrics["g_vtx"] or metrics["g_settimg"]):
            raise ImportError(f"emitted state-only root {name} unexpectedly reaches geometry or texture data")
        emitted_root_reports.append({
            "name": name,
            "ram_address": f"0x{address:08X}",
            "geometry": geometry,
            "reachable_display_lists": metrics["display_lists"],
            "reachable_commands": metrics["commands"],
            "reachable_g_vtx": metrics["g_vtx"],
            "reachable_g_settimg": metrics["g_settimg"],
        })
        seen_emitted_names.add(name)
        seen_emitted_addresses.add(address)

    emitted_ranges = emitted_display_list_ranges or []
    if len(emitted_ranges) != 1:
        raise ImportError(f"expected the one traced renderer-emitted display-list range, found {len(emitted_ranges)}")
    emitted_range_reports = []
    range_config = emitted_ranges[0]
    range_name = str(range_config.get("name", ""))
    range_start = _configured_int(range_config["ram_start"], f"{range_name} emitted display-list range start")
    stride = _configured_int(range_config["stride"], f"{range_name} emitted display-list range stride")
    expected_roots = [
        _configured_int(root, f"{range_name} expected emitted root")
        for root in range_config["expected_roots"]
    ]
    geometry = range_config.get("geometry")
    if not range_name or not isinstance(geometry, bool) or stride < 8 or stride % 8 or len(expected_roots) != 8:
        raise ImportError(f"emitted display-list range {range_name!r} must define eight aligned roots and a valid stride")
    calculated_roots = [range_start + index * stride for index in range(len(expected_roots))]
    if calculated_roots != expected_roots or len(set(expected_roots)) != len(expected_roots):
        raise ImportError(f"emitted display-list range {range_name} does not match its checked roots")
    for index, address in enumerate(expected_roots):
        _segment_offset(address, segment_ram_start, len(hydrated), f"emitted display-list range {range_name}[{index}]")
        if address % 8:
            raise ImportError(f"emitted display-list range {range_name}[{index}] is not 8-byte aligned")
    metrics = inspect_graph(expected_roots, range_name)
    if geometry and metrics["g_vtx"] == 0:
        raise ImportError(f"emitted geometry range {range_name} has no reachable G_VTX commands")
    if not geometry and (metrics["g_vtx"] or metrics["g_settimg"]):
        raise ImportError(f"emitted state-only range {range_name} unexpectedly reaches geometry or texture data")
    emitted_range_reports.append({
        "name": range_name,
        "roots": [f"0x{address:08X}" for address in expected_roots],
        "stride": f"0x{stride:X}",
        "geometry": geometry,
        "reachable_display_lists": metrics["display_lists"],
        "reachable_commands": metrics["commands"],
        "reachable_g_vtx": metrics["g_vtx"],
        "reachable_g_settimg": metrics["g_settimg"],
    })

    # The frontend asynchronously clears two startup framebuffers in this range.
    # Required racer/item commands, vertices and textures must never alias it.
    startup_start, startup_end = 0x80700000, 0x8074B000
    graph_ranges = [(address, address + 8) for address in unique_commands]
    for address in unique_vertex_commands:
        w0, w1 = struct.unpack_from(">II", hydrated, address - segment_ram_start)
        graph_ranges.append((w1 | 0x80000000, (w1 | 0x80000000) + ((w0 >> 10) & 63) * 16))
    for address in unique_texture_commands:
        _, w1 = struct.unpack_from(">II", hydrated, address - segment_ram_start)
        # A full TMEM load is a conservative bound for these validated CI/RGBA maps.
        graph_ranges.append((w1 | 0x80000000, (w1 | 0x80000000) + 4096))
    if any(begin < startup_end and end > startup_start for begin, end in graph_ranges):
        raise ImportError("required visual graph overlaps frontend startup framebuffers")

    missing_armature_roots = sorted({root["address"] for root in model_display_list_roots} - unique_display_lists)
    if missing_armature_roots:
        raise ImportError("untraversed animated-model roots: " + ", ".join(f"0x{x:08X}" for x in missing_armature_roots))

    return bytes(hydrated), {
        "packages": package_reports,
        "stock_relocations": stock_relocations,
        "code_patches": applied_code_patches,
        "cpu_pointer_hydration": {
            "tables": normalized_tables,
            "animation_structures": len(animation_addresses),
            "armature_structures": len(armature_addresses),
            "armature_model_roots": [
                {"name": root["name"], "address": f"0x{root['address'] & 0x00FFFFFF:06X}"}
                for root in model_display_list_roots
            ],
            "external_armature_model_roots": [
                {"name": root["name"], "address": f"0x{root['address'] & 0x00FFFFFF:06X}"}
                for root in external_model_roots
            ],
        },
        "gbi_address_normalizations": {
            kind: len(addresses) for kind, addresses in normalized_gbi_addresses.items()
        },
        "static_display_list_tables": static_table_reports,
        "item_display_list_roots": item_reports,
        "emitted_display_list_roots": emitted_root_reports,
        "emitted_display_list_ranges": emitted_range_reports,
        "external_armature_graph": {
            "display_lists": external_model_metrics["display_lists"],
            "commands": external_model_metrics["commands"],
            "g_vtx": external_model_metrics["g_vtx"],
            "g_settimg": external_model_metrics["g_settimg"],
            "g_settimg_pointers": sorted(set(external_model_metrics["g_settimg_pointers"])),
        },
        "reachable_graph": {
            "display_lists": len(unique_display_lists),
            "required_visual_end": f"0x{max(end for _, end in graph_ranges):08X}",
            "startup_framebuffers_disjoint": True,
            "unique_command_addresses": len(unique_commands),
            "unique_g_vtx_commands": len(unique_vertex_commands),
            "unique_g_vtx_local_relocations": len(unique_local_vertex_commands),
            "unique_g_vtx_fixed_segment_references": len(unique_fixed_vertex_commands),
            "unique_g_settimg_commands": len(unique_texture_commands),
            "g_settimg_pointers": sorted(all_texture_pointers),
            "unique_g_branch_z_commands": len(unique_branch_z_commands),
        },
    }


def import_rom(source_path: Path, patch_path: Path, output_dir: Path, config_path: Path = DEFAULT_CONFIG) -> dict:
    config = load_config(config_path)
    source, patch, result = read_expected_inputs(source_path, patch_path, config)
    start, ram_start, length = validate_segment_layout(config["segment"], config["retail_memory"], len(result.target))
    end = start + length
    raw_segment = result.target[start:end]
    hydrated_segment, hydration = hydrate_model_packages(
        result.target,
        raw_segment,
        ram_start,
        config["model_package_table"],
        config["model_packages"],
        config.get("cpu_pointer_tables", []),
        config.get("cpu_pointer_roots", []),
        config.get("code_patches", []),
        config.get("model_static_display_list_tables", []),
        config.get("model_emitted_display_list_roots", []),
        config.get("model_emitted_display_list_ranges", []),
        config.get("item_display_list_roots", []),
    )

    tables = []
    for table in config["tables"]:
        address = int(table["ram_address"], 16)
        count = int(table["entries"])
        table_offset = address - ram_start
        table_end = table_offset + count * 4
        if address < ram_start or table_end > len(hydrated_segment):
            raise ImportError(f"configured table {table['name']} is outside the custom segment")
        pointers = struct.unpack_from(">" + "I" * count, hydrated_segment, table_offset)
        try:
            for pointer in pointers:
                _segment_virtual_address(pointer, ram_start, length, f"configured table {table['name']} pointer")
        except ImportError as exc:
            raise ImportError(f"configured table {table['name']} contains an out-of-segment pointer") from exc
        tables.append({"name": table["name"], "ram_address": f"0x{address:08X}", "pointers": [f"0x{x:08X}" for x in pointers]})

    raw_racer_colour_records = []
    for table in config.get("raw_racer_colour_records", []):
        address = int(table["ram_address"], 16)
        count = int(table["entries"])
        stride = int(table["stride"])
        fields = int(table["fields"])
        table_offset = start + address - ram_start
        table_end = table_offset + count * stride
        if address < ram_start or table_end > end or fields * 2 > stride:
            raise ImportError("configured raw racer-record table is outside the custom segment")
        records = [
            list(struct.unpack_from(">" + "h" * fields, result.target, table_offset + i * stride))
            for i in range(count)
        ]
        raw_racer_colour_records.append({"ram_address": f"0x{address:08X}", "records_s16": records})

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "amped_up_v3.21.z64"
    segment_path = output_dir / "amped_up_custom_segment.bin"
    raw_segment_path = output_dir / "amped_up_custom_segment.raw.bin"
    atomic_write(target_path, result.target)
    atomic_write(raw_segment_path, raw_segment)
    atomic_write(segment_path, hydrated_segment)
    raw_segment_hash = sha256(raw_segment)
    hydrated_segment_hash = sha256(hydrated_segment)
    report = {
        "source_sha256": sha256(source),
        "patch_sha256": sha256(patch),
        "target_sha256": sha256(result.target),
        "source_crc32": f"{result.source_crc32:08X}",
        "target_crc32": f"{result.target_crc32:08X}",
        "patch_crc32": f"{result.patch_crc32:08X}",
        "target_size": len(result.target),
        "segment_rom_start": f"0x{start:06X}",
        "segment_ram_start": f"0x{ram_start:08X}",
        "segment_size": f"0x{length:X}",
        "raw_segment_sha256": raw_segment_hash,
        "hydrated_segment_sha256": hydrated_segment_hash,
        "model_tables": tables,
        "raw_racer_colour_records": raw_racer_colour_records,
        "model_package_hydration": hydration,
        "outputs": {
            "patched_rom": str(target_path),
            "raw_custom_segment": str(raw_segment_path),
            "custom_segment": str(segment_path),
        },
    }
    atomic_write(output_dir / "import-report.json", (json.dumps(report, indent=2) + "\n").encode())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True, help="user-provided original North American MK64 .z64 ROM")
    parser.add_argument("--patch", type=Path, required=True, help="official Amped Up v3.21 .bps extracted from its archive")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "amped_up", help="private generated files directory")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="checked-in importer metadata")
    args = parser.parse_args(argv)
    try:
        report = import_rom(args.rom, args.patch, args.output_dir, args.config)
    except ImportError as exc:
        print(f"Amped Up import failed: {exc}", file=sys.stderr)
        return 2
    print(f"verified ROM {report['target_sha256']} ({report['target_size']} bytes)")
    print(
        f"hydrated model/code segment {report['segment_size']} at {report['segment_ram_start']}; "
        f"sha256 {report['hydrated_segment_sha256']}"
    )
    print(f"raw segment sha256 {report['raw_segment_sha256']}")
    pointer_entries = sum(len(table["pointers"]) for table in report["model_tables"])
    racer_record_entries = sum(len(table["records_s16"]) for table in report["raw_racer_colour_records"])
    package_graph = report["model_package_hydration"]["reachable_graph"]
    print(
        f"validated {pointer_entries} model pointers, {racer_record_entries} raw racer records, "
        f"and {package_graph['display_lists']} display lists"
    )
    print(f"private import outputs: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
