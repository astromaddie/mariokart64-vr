#!/usr/bin/env python3
"""Integration checks against the supplied retail ROM and official BPS patch."""

from __future__ import annotations

import argparse
import copy
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from generate_model_elf import generate
from importer import (
    DEFAULT_CONFIG,
    ImportError,
    apply_bps,
    hydrate_model_packages,
    import_rom,
    load_config,
    read_expected_inputs,
    validate_segment_layout,
)


class AmpedImporterTests(unittest.TestCase):
    source_path: Path
    patch_path: Path

    def test_official_rom_patch_and_generated_segment(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        source, patch, result = read_expected_inputs(self.source_path, self.patch_path, config)
        self.assertEqual(len(source), 0xC00000)
        self.assertEqual(result.source_crc32, 0x434389C1)
        self.assertEqual(result.target_crc32, 0x711F70F4)

        with tempfile.TemporaryDirectory(prefix="mk64-amped-import-test-") as directory:
            report = import_rom(self.source_path, self.patch_path, Path(directory))
            self.assertEqual(report["target_sha256"], config["rom"]["target_sha256"])
            self.assertEqual(report["segment_size"], "0x32E3B0")
            self.assertEqual(len(report["model_tables"]), 2)
            self.assertEqual([len(table["pointers"]) for table in report["model_tables"]], [8, 34])
            racer_records = report["raw_racer_colour_records"][0]["records_s16"]
            self.assertEqual(len(racer_records), 8)
            self.assertTrue(all(len(record) == 3 for record in racer_records))
            self.assertEqual(racer_records[:4], [[178, 0, 0], [0, 92, 0], [57, 149, 0], [0, 34, 178]])
            self.assertEqual(Path(report["outputs"]["patched_rom"]).stat().st_size, 0x1600000)
            raw_segment = Path(report["outputs"]["raw_custom_segment"]).read_bytes()
            hydrated_segment = Path(report["outputs"]["custom_segment"]).read_bytes()
            self.assertEqual(len(raw_segment), 0x32E3B0)
            self.assertEqual(len(hydrated_segment), 0x32E3B0)
            self.assertEqual(report["raw_segment_sha256"], hashlib.sha256(raw_segment).hexdigest())
            self.assertEqual(
                report["hydrated_segment_sha256"], hashlib.sha256(hydrated_segment).hexdigest()
            )
            self.assertNotEqual(report["raw_segment_sha256"], report["hydrated_segment_sha256"])

            hydration = report["model_package_hydration"]
            self.assertEqual([r["triangles"] for r in hydration["item_display_list_roots"]], [0,51,22,0,53])
            self.assertEqual([r["g_vtx"] for r in hydration["item_display_list_roots"]], [0,3,2,0,5])
            # The item import changes only addresses, never source mesh/color bytes.
            # Measure actual triangle vertices (not the cull-box vertex loads).
            for root in (0x804C8C48, 0x804C8AB8, 0x804C7ED0):
                cache = {}; points = []
                for address in range(root, root + 1024, 8):
                    w0, w1 = struct.unpack_from(">II", hydrated_segment, address - 0x80400000)
                    op = w0 >> 24
                    if op == 0xB8: break
                    if op == 4:
                        count = (w0 >> 10) & 63; first = (w0 >> 17) & 127
                        data = hydrated_segment[w1 - 0x400000:w1 - 0x400000 + count*16]
                        self.assertEqual(data, raw_segment[w1 - 0x400000:w1 - 0x400000 + count*16])
                        for i in range(count): cache[first+i] = struct.unpack_from(">hhh", data, i*16)
                    if op in (0xBF, 0xB1):
                        for word in ((w0,w1) if op == 0xB1 else (w1,)):
                            points.extend(cache[((word >> shift) & 255)//2] for shift in (16,8,0))
                origin = points[0]
                vectors = [tuple(p[i]-origin[i] for i in range(3)) for p in points]
                a = next(v for v in vectors if any(v))
                normals = [(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]) for b in vectors]
                normal = next(n for n in normals if any(n))
                self.assertTrue(any(sum(n*v for n,v in zip(normal,b)) != 0 for b in vectors))
            packages = hydration["packages"]
            self.assertEqual(len(packages), 8)
            self.assertEqual([package["row_index"] for package in packages], list(range(2, 64, 8)))
            self.assertTrue(all(package["row_marker"] == "0x00000000" for package in packages))
            self.assertTrue(all(package["display_list_entries"] == 9 for package in packages))
            self.assertTrue(all(package["nonempty_display_list_entries"] > 0 for package in packages))
            self.assertTrue(all(package["reachable_g_vtx"] > 0 for package in packages))
            self.assertTrue(all(package["g_vtx_local_relocations"] > 0 for package in packages))
            self.assertGreater(hydration["stock_relocations"]["g_dl"], 0)
            self.assertEqual(hydration["stock_relocations"]["g_settimg"], 0)  # normal skins use shared segment textures
            self.assertEqual(hydration["reachable_graph"]["display_lists"], 328)
            self.assertEqual(hydration["reachable_graph"]["unique_command_addresses"], 4788)
            self.assertEqual(hydration["reachable_graph"]["unique_g_vtx_commands"], 471)
            self.assertEqual(hydration["reachable_graph"]["unique_g_vtx_local_relocations"], 314)
            self.assertEqual(hydration["reachable_graph"]["unique_g_vtx_fixed_segment_references"], 157)
            self.assertEqual(hydration["reachable_graph"]["unique_g_settimg_commands"], 18)
            self.assertEqual(
                hydration["reachable_graph"]["g_settimg_pointers"],
                ["0x4C9218", "0x4C92F8", "0x5B05E8", "0x5B0600", "0x5B3870", "0x5B3888", "0x5B6CF8", "0x5B6D18",
                 "0x5B9490", "0x5B94B0", "0x5BC878", "0x5BC898", "0x5BFCF8", "0x5BFD18",
                 "0x5C3178", "0x5C3198", "0x5C65F0", "0x5C6610"],
            )
            self.assertEqual(hydration["reachable_graph"]["unique_g_branch_z_commands"], 0)
            self.assertEqual(hydration["external_armature_graph"]["display_lists"], 11)
            self.assertEqual(hydration["external_armature_graph"]["g_vtx"], 4)

            cpu = hydration["cpu_pointer_hydration"]
            self.assertEqual(cpu["animation_structures"], 35)
            self.assertEqual(cpu["armature_structures"], 10)
            self.assertEqual(len(cpu["armature_model_roots"]), 60)
            self.assertEqual(
                cpu["external_armature_model_roots"],
                [
                    {"name": "secondary_mario_armature.limb_5,secondary_mario_armature.limb_8", "address": "0x5AA700"},
                    {"name": "secondary_mario_armature_alt.limb_5,secondary_mario_armature_alt.limb_8", "address": "0x5AA9F0"},
                ],
            )
            self.assertEqual(len(hydration["code_patches"]), 15)
            self.assertEqual(
                hydration["gbi_address_normalizations"],
                {"g_dl": 293, "g_vtx": 471, "g_settimg": 18, "g_branch_z": 0},
            )
            static_tables = hydration["static_display_list_tables"]
            self.assertEqual(
                [table["name"] for table in static_tables],
                ["character_lod_far", "character_lod_near", "package_alternate_start_a", "package_alternate_start_b"],
            )
            self.assertEqual(static_tables[1]["roots"][0], "0x5ADE80")
            self.assertEqual(static_tables[1]["reachable_display_lists"], 9)
            self.assertEqual(static_tables[1]["reachable_g_vtx"], 26)
            self.assertEqual(static_tables[1]["reachable_g_branch_z"], 0)

            emitted_roots = hydration["emitted_display_list_roots"]
            self.assertEqual(len(emitted_roots), 8)
            self.assertEqual(
                [root["ram_address"] for root in emitted_roots],
                ["0x805ADA30", "0x805AADC0", "0x805AADF0", "0x805ABB88", "0x805ABB30",
                 "0x805ABB60", "0x805A89B8", "0x805A8160"],
            )
            state_root = emitted_roots[0]
            self.assertFalse(state_root["geometry"])
            self.assertEqual(state_root["reachable_g_vtx"], 0)
            self.assertTrue(
                all(root["geometry"] and root["reachable_g_vtx"] > 0 for root in emitted_roots[1:])
            )
            indexed_state = hydration["emitted_display_list_ranges"][0]
            self.assertEqual(
                indexed_state["roots"],
                ["0x805AD880", "0x805AD8B0", "0x805AD8E0", "0x805AD910",
                 "0x805AD940", "0x805AD970", "0x805AD9A0", "0x805AD9D0"],
            )
            self.assertFalse(indexed_state["geometry"])
            self.assertEqual(indexed_state["reachable_g_vtx"], 0)

            # This concrete package-local F3DEX G_VTX reference was not handled
            # by the stock loader's 0x06/0xFD scan. It must resolve into the
            # copied model block before the importer accepts the graph.
            segment_base = int(report["segment_ram_start"], 16)
            root = 0x805C6E10
            root_offset = root - segment_base
            root_w0, root_w1 = struct.unpack_from(">II", hydrated_segment, root_offset)
            self.assertEqual((root_w0, root_w1), (0x06000000, 0x005CAB50))
            vertex_command = 0x805CAB78 - segment_base
            vertex_w0, vertex_w1 = struct.unpack_from(">II", hydrated_segment, vertex_command)
            self.assertEqual((vertex_w0, vertex_w1), (0x040081FF, 0x005CAC98))
            self.assertEqual(raw_segment[root_offset : root_offset + 8], bytes(8))

            # Retain the previous LOD-path regression with the corresponding
            # command in the normal package: its alternate +0x70 selector
            # reaches this ROM vertex operand, which must resolve into copied RAM.
            lod_table = 0x805A46E0 - segment_base
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, lod_table)[0], 0x805ADE80)
            source_lod_vertex = struct.unpack_from(">II", result.target, 0x14971B8)
            self.assertEqual(source_lod_vertex, (0x040079DF, 0x01497228))
            lod_vertex = 0x805C7888 - segment_base
            lod_vertex_w0, lod_vertex_w1 = struct.unpack_from(">II", hydrated_segment, lod_vertex)
            self.assertEqual((lod_vertex_w0, lod_vertex_w1), (0x040079DF, 0x005C78F8))

            effect_limit = 0x804ADE54 - segment_base
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, effect_limit)[0], 0x28660294)

            # These emitted roots were outside the initial package, armature,
            # and pointer-table graph. Hydration canonicalizes their shared
            # segment-0 vertex and nested display-list operands as well.
            static_vertex_command = 0x805AADC8 - segment_base
            self.assertEqual(
                struct.unpack_from(">II", hydrated_segment, static_vertex_command),
                (0x0400207F, 0x005AD7A0),
            )
            nested_static_list_command = 0x805AADE0 - segment_base
            self.assertEqual(
                struct.unpack_from(">II", hydrated_segment, nested_static_list_command),
                (0x06000000, 0x005AAE18),
            )

            skeleton_table = 0x805A4740 - segment_base
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, skeleton_table)[0], 0x005A526C)
            mario_armature_model = 0x805A5280 - segment_base
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, mario_armature_model)[0], 0x005C6E10)
            animation_table = 0x805A5400 - segment_base
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, animation_table)[0], 0x005A5488)
            animation_angle_array = 0x805A5488 + 12 - segment_base
            animation_cycle_array = 0x805A5488 + 16 - segment_base
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, animation_angle_array)[0], 0x005A6200)
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, animation_cycle_array)[0], 0x005A6188)
            # The race helper selects beyond character-count entries: all 34
            # Animation records and both nested operands must be stock-safe.
            for index in range(34):
                token = struct.unpack_from(">I", hydrated_segment, animation_table + index * 4)[0]
                self.assertEqual(token >> 24, 0)
                for field in (12, 16):
                    nested = struct.unpack_from(">I", hydrated_segment, token + 0x80000000 - segment_base + field)[0]
                    self.assertEqual(nested >> 24, 0)
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, 0x805AA700 + 12 - segment_base)[0], 0x005AA748)

    def test_live_effect_rgb_addresses_for_all_players(self) -> None:
        """Execute the actual imported MIPS load block, including the old black path."""
        config = load_config(DEFAULT_CONFIG)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        base = int(config["segment"]["ram_start"], 16)
        start = int(config["segment"]["rom_start"], 16)
        raw = result.target[start:start + int(config["segment"]["length"], 16)]
        changed = bytearray(raw)
        for patch in config["code_patches"]:
            struct.pack_into(">I", changed, int(patch["address"], 16) - base,
                             int(patch["replacement_word"], 16))
        self.assertEqual(raw[0x804AC248-base:0x804AC25A-base], bytes(18))

        def run(segment, player, effect_row, rgb):
            registers = [0] * 32
            registers[2], registers[18] = effect_row, player
            reads = []
            for pc in range(0x805A7848, 0x805A7874, 4):
                word = struct.unpack_from(">I", segment, pc-base)[0]
                op, rs, rt, rd = word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
                imm = (word & 0xffff) - (0x10000 if word & 0x8000 else 0)
                if op == 0 and word & 63 == 0:
                    registers[rd] = registers[rt] << ((word >> 6) & 31)
                elif op == 0 and word & 63 == 0x21:
                    registers[rd] = registers[rs] + registers[rt]
                elif op == 0 and word & 63 == 0x2b:
                    registers[rd] = int(registers[rs] < registers[rt])
                elif op == 9:
                    registers[rt] = registers[rs] + imm
                elif op == 15:
                    registers[rt] = (word & 0xffff) << 16
                elif op == 0x21:
                    address = registers[rs] + imm
                    reads.append(address)
                    registers[rt] = rgb.get(address, struct.unpack_from(">h", segment, address-base)[0]
                                                if base <= address < base+len(segment) else -1)
                else:
                    self.fail(f"unexpected effect-load instruction {word:08X}")
                registers[0] = 0
            return tuple(registers[i] for i in (3, 4, 5)), reads

        for phase in range(4):
            # Distinct live values make a wrong player, channel, or stale custom
            # table address observable. These are inputs, not a copied algorithm.
            palette = {0x80164B10 + channel*16 + player*2: 17+phase*29+channel*3+player
                       for channel in range(3) for player in range(8)}
            for player in range(8):
                for effect in (0, 0x200):
                    old, _ = run(raw, player, effect, palette)
                    self.assertEqual(old, (0, 0, 0))
                    actual, addresses = run(changed, player, effect, palette)
                    expected = [0x80164B10 + player*2 + channel*16 for channel in range(3)]
                    self.assertEqual(addresses, expected)
                    self.assertEqual(actual, tuple(palette[address] for address in expected))

    def test_rejects_wrong_retail_input_before_writing_outputs(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory(prefix="mk64-amped-wrong-rom-") as directory:
            wrong_rom = Path(directory) / "wrong.z64"
            data = bytearray(self.source_path.read_bytes())
            data[0x100] ^= 1
            wrong_rom.write_bytes(data)
            with self.assertRaisesRegex(ImportError, "source ROM SHA-256"):
                import_rom(wrong_rom, self.patch_path, Path(directory) / "out")
            self.assertFalse((Path(directory) / "out" / "amped_up_v3.21.z64").exists())
            self.assertEqual(config["rom"]["source_sha256"], "d6b8538dd63f0132ecb2856e7d32816ed3c30e3e479aecd23cf83fb6ba17a5da")

    def test_rejects_truncated_bps_stream(self) -> None:
        patch = self.patch_path.read_bytes()
        with self.assertRaises(ImportError):
            apply_bps(self.source_path.read_bytes(), patch[:-7])

    def test_rejects_segment_that_overlaps_retail_static_memory(self) -> None:
        config_text = DEFAULT_CONFIG.read_text(encoding="utf-8")
        config_text = config_text.replace('static_noload_end = "0x803FFDB0"', 'static_noload_end = "0x80401000"')
        with tempfile.TemporaryDirectory(prefix="mk64-amped-overlap-") as directory:
            config_path = Path(directory) / "models.toml"
            config_path.write_text(config_text, encoding="utf-8")
            with self.assertRaisesRegex(ImportError, "overlaps original retail heap or static memory"):
                import_rom(self.source_path, self.patch_path, Path(directory) / "out", config_path)
            self.assertFalse((Path(directory) / "out").exists())

    def test_rejects_overlapping_model_package_destinations(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, ram_start, length = validate_segment_layout(config["segment"], config["retail_memory"], 0x1600000)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        raw_segment = result.target[int(config["segment"]["rom_start"], 16) : int(config["segment"]["rom_start"], 16) + length]
        broken_table = bytearray(raw_segment)
        packages = copy.deepcopy(config["model_packages"])
        packages[1]["ram_address"] = packages[0]["ram_address"]
        table_offset = int(config["model_package_table"]["ram_address"], 16) - ram_start
        struct.pack_into(">I", broken_table, table_offset + packages[1]["row_index"] * 16 + 4, int(packages[0]["ram_address"], 16))
        with self.assertRaisesRegex(ImportError, "overlaps luigi in RAM"):
            hydrate_model_packages(
                result.target,
                bytes(broken_table),
                ram_start,
                config["model_package_table"],
                packages,
                static_display_list_tables=config["model_static_display_list_tables"],
                emitted_display_list_roots=config["model_emitted_display_list_roots"],
                emitted_display_list_ranges=config["model_emitted_display_list_ranges"],
            )

    def test_default_skin_descriptor_matches_selected_packages(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        def words(ram, fmt):
            return struct.unpack_from(fmt, result.target, ram - 0x80400000 + 0xE00000)
        self.assertEqual(config["model_package_table"]["selected_slot"], 2)
        self.assertEqual(config["model_package_table"]["entry_stride"], 16)
        for character, package in enumerate(config["model_packages"]):
            descriptor = 0x805A5D08 + character * 16
            self.assertEqual(words(descriptor, ">I")[0], 0x805A5D88 + character * 128)
            self.assertEqual(words(descriptor + 8, ">H")[0], 2)
            self.assertEqual(package["row_index"], character * 8 + 2)
            start = int(package["rom_start"], 16)
            for selector in range(9):
                op, address, end, unused = struct.unpack_from(">4I", result.target, start + selector * 16)
                self.assertIn(op, (0x06000000, 0xB8000000))
                self.assertEqual((end, unused), (0xB8000000, 0))

    def test_rejects_unresolved_animated_limb_beyond_first_five_selectors(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        rom, ram, length = validate_segment_layout(config["segment"], config["retail_memory"], len(result.target))
        bad = bytearray(result.target)
        # Mario's +0x50 selector reaches this actual limb vertex command. The
        # former eight-byte stride stopped at +0x40 and missed this entire limb.
        self.assertEqual(struct.unpack_from(">II", bad, 0x14996C8), (0x0400617F, 0x01499760))
        struct.pack_into(">I", bad, 0x14996C8 + 4, 0x01700000)
        with self.assertRaisesRegex(ImportError, "mario G_VTX.*0x01700000"):
            hydrate_model_packages(bytes(bad), bytes(bad[rom:rom+length]), ram,
                config["model_package_table"], config["model_packages"],
                config["cpu_pointer_tables"], config["cpu_pointer_roots"], config["code_patches"],
                config["model_static_display_list_tables"], config["model_emitted_display_list_roots"],
                config["model_emitted_display_list_ranges"])

    def test_rejects_reachable_unresolved_package_vertex_reference(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        rom_start, ram_start, length = validate_segment_layout(config["segment"], config["retail_memory"], len(result.target))
        raw_segment = result.target[rom_start : rom_start + length]
        corrupted_target = bytearray(result.target)
        struct.pack_into(">I", corrupted_target, 0x149A4A8 + 4, 0x01700000)
        with self.assertRaisesRegex(ImportError, "not a segment-0/KSEG0 pointer: 0x01700000"):
            hydrate_model_packages(
                bytes(corrupted_target),
                raw_segment,
                ram_start,
                config["model_package_table"],
                config["model_packages"],
                static_display_list_tables=config["model_static_display_list_tables"],
                emitted_display_list_roots=config["model_emitted_display_list_roots"],
                emitted_display_list_ranges=config["model_emitted_display_list_ranges"],
            )

    def test_rejects_unresolved_vertex_selected_by_static_lod_root(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        rom_start, ram_start, length = validate_segment_layout(config["segment"], config["retail_memory"], len(result.target))
        raw_segment = result.target[rom_start : rom_start + length]
        corrupted_target = bytearray(result.target)
        # This G_VTX at the fixed Mario near-LOD root is outside the
        # package-entry/armature roots; forcing an unresolved operand must now
        # fail while the production graph walks the checked static table.
        struct.pack_into(">I", corrupted_target, 0xFADEA0 + 4, 0x01700000)
        raw_segment = bytes(corrupted_target[rom_start : rom_start + length])
        with self.assertRaisesRegex(ImportError, "character_lod_near G_VTX at 0x805ADEA0.*0x01700000"):
            hydrate_model_packages(
                bytes(corrupted_target),
                raw_segment,
                ram_start,
                config["model_package_table"],
                config["model_packages"],
                config["cpu_pointer_tables"],
                config["cpu_pointer_roots"],
                config["code_patches"],
                config["model_static_display_list_tables"],
                config["model_emitted_display_list_roots"],
                config["model_emitted_display_list_ranges"],
            )

    def test_rejects_unresolved_vertex_in_emitted_literal_root(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        rom_start, ram_start, length = validate_segment_layout(
            config["segment"], config["retail_memory"], len(result.target)
        )
        raw_segment = bytearray(result.target[rom_start : rom_start + length])
        # This shared-geometry G_VTX belongs to the renderer's direct
        # 0x805AADC0 root, outside the package and four static-table closures.
        command_offset = 0x805AADC8 - ram_start
        struct.pack_into(">I", raw_segment, command_offset + 4, 0x01700000)
        with self.assertRaisesRegex(
            ImportError,
            "character_detail_a G_VTX at 0x805AADC8.*0x01700000",
        ):
            hydrate_model_packages(
                result.target,
                bytes(raw_segment),
                ram_start,
                config["model_package_table"],
                config["model_packages"],
                config["cpu_pointer_tables"],
                config["cpu_pointer_roots"],
                config["code_patches"],
                config["model_static_display_list_tables"],
                config["model_emitted_display_list_roots"],
                config["model_emitted_display_list_ranges"],
            )

    def test_rejects_typed_cpu_pointer_outside_segment(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, ram_start, length = validate_segment_layout(config["segment"], config["retail_memory"], 0x1600000)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        rom_start = int(config["segment"]["rom_start"], 16)
        raw_segment = bytearray(result.target[rom_start : rom_start + length])
        skeleton_table_offset = int(config["cpu_pointer_tables"][0]["ram_address"], 16) - ram_start
        struct.pack_into(">I", raw_segment, skeleton_table_offset, 0x007FFFFC)
        with self.assertRaisesRegex(ImportError, "CPU pointer table skeletons\\[0\\] points outside"):
            hydrate_model_packages(
                result.target,
                bytes(raw_segment),
                ram_start,
                config["model_package_table"],
                config["model_packages"],
                config["cpu_pointer_tables"],
                config["cpu_pointer_roots"],
                config["code_patches"],
                config["model_static_display_list_tables"],
                config["model_emitted_display_list_roots"],
                config["model_emitted_display_list_ranges"],
            )

    def test_articulated_renderer_preserves_all_player_arguments(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        base = int(config["segment"]["ram_start"], 16)
        rom = int(config["segment"]["rom_start"], 16)
        data = bytearray(result.target[rom:rom + int(config["segment"]["length"], 16)])
        for patch in config["code_patches"]:
            offset = int(patch["address"], 16) - base
            self.assertEqual(struct.unpack_from(">I", data, offset)[0], int(patch["expected_word"], 16))
            struct.pack_into(">I", data, offset, int(patch["replacement_word"], 16))
        def word(pc):
            return struct.unpack_from(">I", data, pc - base)[0]
        # The remote path must retain the original visibility rejection before
        # the new selector; alpha remains restored by the branch delay slot.
        self.assertEqual(word(0x805A7730), 0x4501FF90)
        self.assertEqual(word(0x805A7740), 0x8FA80078)
        for start in (0x805A7490, 0x805A7738):
            for player in range(8):
                for character in range(8):
                    regs = [0] * 32
                    regs[29] = 0x80300000
                    regs[2] = 0x80410000
                    regs[18], regs[19], regs[22], regs[17] = player, character, 0x800F6990 + player * 0xDD8, 0
                    regs[7] = 137
                    stack = {0x68: 31, 0x64: 47, 0x60: 59, 0x74: 71, 0x70: 83, 0x6C: 97,
                             0x78: 137, 0xB4: 3}
                    calls, pc = [], start
                    def step(ins):
                        op, rs, rt = ins >> 26, (ins >> 21) & 31, (ins >> 16) & 31
                        imm = (ins & 0xFFFF) - (0x10000 if ins & 0x8000 else 0)
                        if op == 32:
                            offset = regs[rs] + imm - base
                            regs[rt] = struct.unpack_from("b", data, offset)[0]
                        elif op == 35 and rs == 29: regs[rt] = stack[imm]
                        elif op == 43 and rs == 29: stack[imm] = regs[rt]
                        elif op == 9: regs[rt] = regs[rs] + imm
                        elif op == 15: regs[rt] = (ins & 0xFFFF) << 16
                        elif op == 0 and ins & 63 in (0x21, 0x25):
                            regs[(ins >> 11) & 31] = regs[rs] + regs[rt] if ins & 63 == 0x21 else regs[rs] | regs[rt]
                        elif ins: self.fail(f"unhandled setup instruction {ins:08X}")
                        regs[0] = 0
                    for _ in range(100):
                        ins = word(pc)
                        if ins >> 26 == 4:  # checked unconditional BEQ zero,zero
                            self.assertEqual(ins & 0xFFFF0000, 0x10000000)
                            step(word(pc + 4))
                            offset = (ins & 0xFFFF) - (0x10000 if ins & 0x8000 else 0)
                            pc += 4 + offset * 4
                        elif ins >> 26 == 3:
                            step(word(pc + 4))
                            target = 0x80000000 | ((ins & 0x3FFFFFF) << 2)
                            calls.append(target)
                            self.assertEqual(regs[4:8], [0x800F6990 + player * 0xDD8, player, 0, 3])
                            self.assertEqual(stack[0x10], character)
                            if len(calls) == 1:
                                self.assertEqual([stack[n] for n in (0x20,0x24,0x28,0x2C,0x30,0x34,0x38)],
                                                 [97,83,71,59,47,31,137])
                            pc += 8
                            if len(calls) == 2: break
                        else:
                            step(ins)
                            pc += 4
                    self.assertEqual(calls, [0x805A6650, 0x805A6D30])

    def test_generated_entrypoints_obey_o32_and_use_base_callback(self) -> None:
        build_root = DEFAULT_CONFIG.parents[2] / "build" / "amped_up"
        build_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="abi-check-", dir=build_root) as directory:
            output = Path(directory)
            import_rom(self.source_path, self.patch_path, output)
            generated = generate(
                DEFAULT_CONFIG,
                output / "amped_up_custom_segment.bin",
                output / "import-report.json",
                output / "amped_up_model.S",
            )
            assembly = (output / "amped_up_model.S").read_text(encoding="utf-8")

        self.assertEqual(generated["function_count"], 14)
        self.assertEqual(generated["extracted_function_count"], 10)
        self.assertEqual(len(generated["function_definitions"]), len(set(generated["function_definitions"])))
        self.assertEqual(len(generated["code_patches"]), 15)

        render_entry = assembly.split("render_kart:\n", 1)[1].split(".size render_kart", 1)[0]
        self.assertIn("addiu $sp, $sp, -32", render_entry)
        self.assertIn("sw $ra, 24($sp)", render_entry)
        self.assertIn("sw $zero, 16($sp)", render_entry)
        self.assertIn("jal amped_model_renderer", render_entry)
        self.assertIn("lw $ra, 24($sp)", render_entry)

        tail_entry = assembly.split("amped_tail_render_animated_model:\n", 1)[1].split(
            ".size amped_tail_render_animated_model", 1
        )[0]
        self.assertIn("addiu $sp, $sp, -24", tail_entry)
        self.assertIn("sw $ra, 20($sp)", tail_entry)
        self.assertIn("jal render_animated_model", tail_entry)
        self.assertIn("sll $a0, $a0, 8", tail_entry)
        self.assertIn("srl $a0, $a0, 8", tail_entry)
        self.assertIn("sll $a1, $a1, 8", tail_entry)
        self.assertIn("srl $a1, $a1, 8", tail_entry)
        self.assertIn("lw $ra, 20($sp)", tail_entry)
        self.assertIn('.section .recomp_callback.*:recomp_on_init,"ax",@progbits', assembly)
        self.assertEqual(assembly.count(".type "), 14)
        self.assertIn(".long 0x3C05005B", assembly)
        self.assertEqual(generated["cpu_load_adapter"], {
            "address": "0x805A6F68", "expected_word": "0x8C46000C",
            "target": "amped_load_animation_angles",
        })
        self.assertEqual(assembly.count("jal amped_load_animation_angles"), 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    args = parser.parse_args()
    AmpedImporterTests.source_path = args.rom
    AmpedImporterTests.patch_path = args.patch
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AmpedImporterTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
