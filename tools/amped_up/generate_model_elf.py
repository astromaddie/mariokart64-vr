#!/usr/bin/env python3
"""Generate a relocatable MIPS source file for Amped Up's traced 3D racer path."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "mods" / "amped_up" / "models.toml"
DEFAULT_SEGMENT = ROOT / "build" / "amped_up" / "amped_up_custom_segment.bin"
DEFAULT_REPORT = ROOT / "build" / "amped_up" / "import-report.json"
DEFAULT_ASSEMBLY = ROOT / "build" / "amped_up" / "amped_up_model.S"


class GenerationError(ValueError):
    pass


def load_config(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def generate(config_path: Path, segment_path: Path, report_path: Path, assembly_path: Path) -> dict:
    config = load_config(config_path)
    segment_path = segment_path.resolve()
    segment = segment_path.read_bytes()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    segment_cfg = config["segment"]
    ram_start = int(segment_cfg["ram_start"], 16)
    expected_size = int(segment_cfg["length"], 16)
    segment_hash = hashlib.sha256(segment).hexdigest()
    if len(segment) != expected_size or segment_hash != report["hydrated_segment_sha256"]:
        raise GenerationError("hydrated custom segment does not match the validated import report")

    functions = config["code_functions"]
    names_by_address: dict[int, str] = {}
    for function in functions:
        address = int(function["start"], 16)
        size = int(function["size"], 16)
        if address % 4 or size <= 0 or size % 4:
            raise GenerationError(f"function {function['name']} has an invalid MIPS extent")
        offset = address - ram_start
        if offset < 0 or offset + size > len(segment):
            raise GenerationError(f"function {function['name']} falls outside the copied segment")
        if address in names_by_address:
            raise GenerationError(f"duplicate function address 0x{address:08X}")
        names_by_address[address] = function["name"]

    external_symbols = {int(address, 16): name for address, name in config["stock_calls"].items()}
    target_names = {**external_symbols, **names_by_address}
    observed_calls: dict[str, list[str]] = {}
    tail_thunks: dict[str, str] = {}
    definition_names = ["render_kart"]
    lines = [
        "# Generated from the privately imported Amped Up v3.21 image; do not edit.",
        ".set noreorder",
        ".set noat",
        "",
        '.section .recomp_force_patch,"ax",@progbits',
        ".globl render_kart",
        ".type render_kart,@function",
        "render_kart:",
        # render_kart supplies four register arguments; the Amped renderer
        # also reads argument five from the O32 outgoing argument area.
        # Keep that 16-byte home area intact and save $ra above it.
        "  addiu $sp, $sp, -32",
        "  sw $ra, 24($sp)",
        "  sw $zero, 16($sp)",
        "  jal amped_model_renderer",
        "  nop",
        "  lw $ra, 24($sp)",
        "  addiu $sp, $sp, 32",
        "  jr $ra",
        "  nop",
        ".size render_kart, .-render_kart",
        "",
        '.section .text.amped_up,"ax",@progbits',
    ]

    for function in functions:
        name = function["name"]
        address = int(function["start"], 16)
        size = int(function["size"], 16)
        offset = address - ram_start
        words = struct.unpack_from(">" + "I" * (size // 4), segment, offset)
        lines += [f".globl {name}", f".type {name},@function", f"{name}:"]
        definition_names.append(name)
        calls: list[str] = []
        for index, word in enumerate(words):
            pc = address + index * 4
            # This helper directly dereferences two fields also consumed by
            # stock segmented_to_virtual. Keep their stored segment-0 form,
            # but restore KSEG0 for the helper's CPU read and steering writes.
            # Its original RA is already saved and restored after this site;
            # the original delay instruction only finishes the armature base.
            if pc == 0x805A6F68:
                if word != 0x8C46000C:
                    raise GenerationError("animation CPU load at 805A6F68 changed")
                lines.append("  jal amped_load_animation_angles")
                continue
            opcode = word >> 26
            if opcode in (2, 3):
                target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
                symbol = target_names.get(target)
                if symbol is None:
                    raise GenerationError(
                        f"untraced direct MIPS call 0x{pc:08X} -> 0x{target:08X} in {name}"
                    )
                calls.append(f"0x{target:08X}:{symbol}")
                emitted_symbol = symbol
                if opcode == 2 and target in external_symbols:
                    emitted_symbol = tail_thunks.setdefault(symbol, f"amped_tail_{symbol}")
                lines.append(f"  {'jal' if opcode == 3 else 'j'} {emitted_symbol}")
            else:
                lines.append(f"  .long 0x{word:08X}")
        lines += [f".size {name}, .-{name}", ""]
        observed_calls[name] = calls

    definition_names.append("amped_load_animation_angles")
    lines += [
        ".globl amped_load_animation_angles",
        ".type amped_load_animation_angles,@function",
        "amped_load_animation_angles:",
        "  lui $at, 0x8000",
        "  or $v0, $v0, $at",
        "  lw $a2, 12($v0)",
        "  jr $ra",
        "  or $a2, $a2, $at",
        ".size amped_load_animation_angles, .-amped_load_animation_angles",
        "",
    ]

    # N64Recomp handles direct JAL calls to reference symbols, but a direct J
    # to a stock reference becomes an unresolved branch. A local MIPS thunk
    # makes that tail-call path explicit while preserving the caller's $ra.
    for target_name, thunk_name in tail_thunks.items():
        definition_names.append(thunk_name)
        lines += [
            f".globl {thunk_name}",
            f".type {thunk_name},@function",
            f"{thunk_name}:",
            # The stock callee may spill all four register arguments into
            # the O32 home area, so keep saved $ra above its 16-byte area.
            "  addiu $sp, $sp, -24",
            "  sw $ra, 20($sp)",
            *(["  sll $a0, $a0, 8", "  srl $a0, $a0, 8", "  sll $a1, $a1, 8", "  srl $a1, $a1, 8"]
              if target_name == "render_animated_model" else []),
            f"  jal {target_name}",
            "  nop",
            "  lw $ra, 20($sp)",
            "  addiu $sp, $sp, 24",
            "  jr $ra",
            "  nop",
            f".size {thunk_name}, .-{thunk_name}",
            "",
        ]

    lines += [
        '.section .recomp_callback.*:recomp_on_init,"ax",@progbits',
        ".globl amped_up_copy_segment",
        ".type amped_up_copy_segment,@function",
        "amped_up_copy_segment:",
        "  lui $t0, %hi(amped_up_segment)",
        "  addiu $t0, $t0, %lo(amped_up_segment)",
        "  lui $t1, 0x8040",
        "  lui $t2, 0x000C",
        "  ori $t2, $t2, 0xB8EC",
        "1:",
        "  lw $t3, 0($t0)",
        "  sw $t3, 0($t1)",
        "  addiu $t0, $t0, 4",
        "  addiu $t1, $t1, 4",
        "  addiu $t2, $t2, -1",
        "  bnez $t2, 1b",
        "  nop",
        "  jr $ra",
        "  nop",
        ".size amped_up_copy_segment, .-amped_up_copy_segment",
        "",
        '.section .data.amped_up,"aw",@progbits',
        ".balign 16",
        ".globl amped_up_segment",
        "amped_up_segment:",
        f'.incbin "{segment_path.relative_to(ROOT).as_posix()}"',
        "",
    ]
    definition_names.append("amped_up_copy_segment")
    if len(definition_names) != len(set(definition_names)):
        raise GenerationError("generated MIPS source contains duplicate function definitions")
    if len(functions) != 10 or len(tail_thunks) != 1 or set(tail_thunks) != {"render_animated_model"}:
        raise GenerationError(
            "the traced model path must contain ten extracted functions and one render_animated_model tail thunk"
        )
    if len(definition_names) != 14:
        raise GenerationError(f"expected 14 unique MIPS function definitions, found {len(definition_names)}")

    assembly_path.parent.mkdir(parents=True, exist_ok=True)
    assembly_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "hydrated_segment_sha256": segment_hash,
        "function_count": len(definition_names),
        "extracted_function_count": len(functions),
        "function_definitions": definition_names,
        "functions": [function["name"] for function in functions],
        "tail_thunks": list(tail_thunks.values()),
        "call_targets": sorted({call.split(":", 1)[1] for calls in observed_calls.values() for call in calls}),
        "calls": observed_calls,
        "code_patches": report["model_package_hydration"]["code_patches"],
        "cpu_load_adapter": {"address": "0x805A6F68", "expected_word": "0x8C46000C",
                             "target": "amped_load_animation_angles"},
        "assembly_path": str(assembly_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--segment", type=Path, default=DEFAULT_SEGMENT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--assembly", type=Path, default=DEFAULT_ASSEMBLY)
    args = parser.parse_args()
    result = generate(args.config, args.segment, args.report, args.assembly)
    print(
        f"generated {result['function_count']} unique function definitions "
        f"({result['extracted_function_count']} extracted) and {len(result['call_targets'])} resolved targets"
    )
    print(f"private MIPS source: {result['assembly_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
