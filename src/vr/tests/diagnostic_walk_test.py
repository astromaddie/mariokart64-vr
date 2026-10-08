#!/usr/bin/env python3
"""Execute the production walker with host-backed logical RDRAM reads."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
source = (root / "patches/frame_report.c").read_text()
walker = source.split("#define DIAGNOSTIC_RDRAM_SIZE", 1)[1].split("void mk64_diag_racer(", 1)[0]
walker = "#define DIAGNOSTIC_RDRAM_SIZE" + walker
# Bind the production external pool symbol to its mapped test allocation. The
# resolver, address checks, recursive walk and top-level span check are unchanged.
walker = walker.replace("extern Gfx gfxPoolExtended[2][GFX_POOL_SIZE * 0x10];", "")
# A host process cannot dereference an N64 virtual address. Adapt only the raw
# memory read; execute the actual address resolver, bounds and traversal code.
read = "u32 w0 = list->words.w0, w1 = list->words.w1;"
assert walker.count(read) == 1
walker = walker.replace(read, "Gfx entry = fixture_read((u32)(uintptr_t)list); u32 w0 = entry.words.w0, w1 = entry.words.w1;")
runtime = (root / "lib/N64ModernRuntime/librecomp/include/librecomp/addresses.hpp").read_text()
assert "mem_size = 512ULL * 1024ULL * 1024ULL" in runtime
pool_source = (root / "patches/gfx_config.c").read_text()
assert "#define GFX_POOL_EXTENDED_SIZE (GFX_POOL_SIZE * 0x10)" in pool_source
assert "gDisplayListHead = gfxPoolExtended[gGlobalTimer & 1];" in pool_source
program = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
typedef uint32_t u32;
typedef union { struct { u32 w0, w1; } words; uint64_t align; } Gfx;
#define GFX_POOL_SIZE 7500
#define gfxPoolExtended (*(Gfx (*)[2][GFX_POOL_SIZE * 0x10])0x8081BAD0u)
u32 gSegmentTable[16];
int gGlobalTimer;
static Gfx* fixture_ram;
static Gfx fixture_read(u32 address) {
    assert(address >= 0x80000000u && address <= 0x9FFFFFF8u && !(address & 7));
    return fixture_ram[(address - 0x80000000u) / sizeof(Gfx)];
}
''' + walker + r'''
static void command(u32 address, u32 op, u32 operand) {
    Gfx* list = &fixture_ram[(address - 0x80000000u) / sizeof(Gfx)];
    list->words.w0 = op;
    list->words.w1 = operand;
}
int main(void) {
    void* ram = mmap(0, DIAGNOSTIC_RDRAM_SIZE,
                    PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(ram != MAP_FAILED);
    fixture_ram = ram;
    Gfx* begin = gfxPoolExtended[0];
    command((u32)(uintptr_t)begin, 0x01000000, 0); // matrix
    command((u32)(uintptr_t)(begin + 1), 0x06000000, 0x805ABC00);
    command((u32)(uintptr_t)(begin + 2), 0xBF000000, 0);
    command(0x805ABC00, 0xB1000000, 0); // two triangles
    command(0x805ABC08, 0x06000000, 0x01000010);
    command(0x805ABC10, 0xB8000000, 0);
    gSegmentTable[1] = 0x00900000;
    command(0x80900010, 0xBF000000, 0);
    command(0x80900018, 0xB8000000, 0);
    RacerDrawStats stats = {0};
    diagnostic_racer_span(begin, begin + 3, &stats);
    assert(!stats.truncated && stats.commands == 8 && stats.triangles == 4);
    assert(stats.matrices == 1 && stats.lists == 2);
    // The last mapped command is readable; one-past, misaligned and unmapped
    // segment tokens fail before a dereference or out-of-bounds segment lookup.
    command(0x9FFFFFF8, 0xB8000000, 0);
    stats = (RacerDrawStats){0};
    diagnostic_walk(diagnostic_list(0x9FFFFFF8, &stats), 0, 0, &stats);
    assert(!stats.truncated && stats.commands == 1);
    const u32 invalid[] = {0xA0000000, 0x7FFFFFF8, 0x80000001, 0x10000000};
    for (unsigned i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        stats = (RacerDrawStats){0};
        assert(!diagnostic_list(invalid[i], &stats));
        assert(stats.failure == 1 && stats.stopped_at == invalid[i]);
    }
    gSegmentTable[15] = 0x1FFFFFF8;
    stats = (RacerDrawStats){0};
    assert(diagnostic_list(0x0F000000, &stats) == (Gfx*)0x9FFFFFF8u);
    assert(!diagnostic_list(0x0F000008, &stats));
    gSegmentTable[15] = 0xFFFFFFF0; // must not wrap into mapped RDRAM
    stats = (RacerDrawStats){0};
    assert(!diagnostic_list(0x0F000020, &stats));
    assert(stats.stopped_at == 0x0F000020);
    stats = (RacerDrawStats){0};
    diagnostic_racer_span((Gfx*)0x805ABC00u, (Gfx*)0x805ABC08u, &stats);
    assert(stats.failure == 4 && stats.commands == 0);
    stats = (RacerDrawStats){0};
    diagnostic_racer_span(begin + 3, begin, &stats);
    assert(stats.failure == 4 && stats.commands == 0);
    command(0x805ABC00, 0x06000000, 0x805ABC00); // cycle has a bounded failure
    stats = (RacerDrawStats){0};
    diagnostic_walk((Gfx*)0x805ABC00u, 0, 0, &stats);
    assert(stats.failure == 2 && stats.commands == 17);
    stats = (RacerDrawStats){0}; stats.commands = 8191;
    diagnostic_walk(begin, begin + 3, 0, &stats);
    assert(stats.failure == 3 && stats.commands == 8192);
    assert(munmap(ram, DIAGNOSTIC_RDRAM_SIZE) == 0);
    puts("production walker: expanded pool, segmented lists, exact counts and bounded failures passed");
}
'''
with tempfile.TemporaryDirectory(prefix="mk64-diagnostic-walk-") as directory:
    code, binary = Path(directory) / "test.c", Path(directory) / "test"
    code.write_text(program)
    command = ["cc", "-std=c11", "-D_DEFAULT_SOURCE", "-Wno-pointer-to-int-cast", "-Wno-int-to-pointer-cast", str(code), "-o", str(binary)]
    subprocess.run(command, check=True)
    subprocess.run([str(binary)], check=True)
