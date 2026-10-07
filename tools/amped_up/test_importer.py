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
            self.assertEqual([len(table["pointers"]) for table in report["model_tables"]], [8, 8])
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
            packages = hydration["packages"]
            self.assertEqual(len(packages), 8)
            self.assertEqual([package["row_index"] for package in packages], list(range(0, 64, 8)))
            self.assertTrue(all(package["row_marker"] == "0xFFFE0000" for package in packages))
            self.assertTrue(all(package["display_list_entries"] == 9 for package in packages))
            self.assertTrue(all(package["nonempty_display_list_entries"] > 0 for package in packages))
            self.assertTrue(all(package["reachable_g_vtx"] > 0 for package in packages))
            self.assertTrue(all(package["g_vtx_local_relocations"] > 0 for package in packages))
            self.assertGreater(hydration["stock_relocations"]["g_dl"], 0)
            self.assertGreater(hydration["stock_relocations"]["g_settimg"], 0)
            self.assertEqual(hydration["reachable_graph"]["display_lists"], 269)
            self.assertEqual(hydration["reachable_graph"]["unique_command_addresses"], 3681)
            self.assertEqual(hydration["reachable_graph"]["unique_g_vtx_commands"], 340)
            self.assertEqual(hydration["reachable_graph"]["unique_g_vtx_local_relocations"], 211)
            self.assertEqual(hydration["reachable_graph"]["unique_g_vtx_fixed_segment_references"], 129)
            self.assertEqual(hydration["reachable_graph"]["unique_g_settimg_commands"], 16)
            self.assertEqual(
                hydration["reachable_graph"]["g_settimg_pointers"],
                ["0x5B05E8", "0x5B0600", "0x5B3870", "0x5B3888", "0x5B6CF8", "0x5B6D18",
                 "0x5B9490", "0x5B94B0", "0x5E5970", "0x5E5990", "0x5EC3E0", "0x5EC400",
                 "0x5F2FF0", "0x5F3010", "0x5FB600", "0x5FB620"],
            )
            self.assertEqual(hydration["reachable_graph"]["unique_g_branch_z_commands"], 0)
            self.assertEqual(hydration["external_armature_graph"]["display_lists"], 11)
            self.assertEqual(hydration["external_armature_graph"]["g_vtx"], 4)

            cpu = hydration["cpu_pointer_hydration"]
            self.assertEqual(cpu["animation_structures"], 9)
            self.assertEqual(cpu["armature_structures"], 10)
            self.assertEqual(len(cpu["armature_model_roots"]), 60)
            self.assertEqual(
                cpu["external_armature_model_roots"],
                [
                    {"name": "secondary_mario_armature.limb_5,secondary_mario_armature.limb_8", "address": "0x5AA700"},
                    {"name": "secondary_mario_armature_alt.limb_5,secondary_mario_armature_alt.limb_8", "address": "0x5AA9F0"},
                ],
            )
            self.assertEqual(len(hydration["code_patches"]), 5)
            self.assertEqual(
                hydration["gbi_address_normalizations"],
                {"g_dl": 191, "g_vtx": 340, "g_settimg": 16, "g_branch_z": 0},
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
            self.assertEqual((root_w0, root_w1), (0x06000000, 0x005CB358))
            vertex_command = 0x805CB380 - segment_base
            vertex_w0, vertex_w1 = struct.unpack_from(">II", hydrated_segment, vertex_command)
            self.assertEqual((vertex_w0, vertex_w1), (0x040081FF, 0x005CB4E8))
            self.assertEqual(raw_segment[root_offset : root_offset + 8], bytes(8))

            # Native frame-811 RSP evidence showed the renderer selecting the
            # Mario LOD table's 0x805ADE80 root and loading a vertex command the
            # eight DMA-entry/armature roots had missed. Resolve that command
            # from the official patched source package into its copied RAM.
            lod_table = 0x805A46E0 - segment_base
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, lod_table)[0], 0x805ADE80)
            source_lod_vertex = struct.unpack_from(">II", result.target, 0x152A350)
            self.assertEqual(source_lod_vertex, (0x04005D6F, 0x0152A3A8))
            lod_vertex = 0x805C7940 - segment_base
            lod_vertex_w0, lod_vertex_w1 = struct.unpack_from(">II", hydrated_segment, lod_vertex)
            self.assertEqual((lod_vertex_w0, lod_vertex_w1), (0x04005D6F, 0x005C7998))

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
            self.assertEqual(struct.unpack_from(">I", hydrated_segment, 0x805AA700 + 12 - segment_base)[0], 0x005AA748)

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

    def test_rejects_reachable_unresolved_package_vertex_reference(self) -> None:
        config = load_config(DEFAULT_CONFIG)
        _, _, result = read_expected_inputs(self.source_path, self.patch_path, config)
        rom_start, ram_start, length = validate_segment_layout(config["segment"], config["retail_memory"], len(result.target))
        raw_segment = result.target[rom_start : rom_start + length]
        corrupted_target = bytearray(result.target)
        struct.pack_into(">I", corrupted_target, 0x152DD90 + 4, 0x01700000)
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
        # This G_VTX at the known Mario near-LOD root is outside the previously
        # covered entry/armature roots; forcing an unresolved operand must now
        # fail while the production graph walks the checked static table.
        struct.pack_into(">I", corrupted_target, 0x152A350 + 4, 0x01700000)
        with self.assertRaisesRegex(ImportError, "package_alternate_start_b G_VTX at 0x805C7940.*0x01700000"):
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

        self.assertEqual(generated["function_count"], 13)
        self.assertEqual(generated["extracted_function_count"], 10)
        self.assertEqual(len(generated["function_definitions"]), len(set(generated["function_definitions"])))
        self.assertEqual(len(generated["code_patches"]), 5)

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
        self.assertEqual(assembly.count(".type "), 13)
        self.assertIn(".long 0x3C05005B", assembly)


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
