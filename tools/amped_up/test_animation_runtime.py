#!/usr/bin/env python3
"""Run the generated full-detail animation helper and stock traversal on host.

Requires build_mod.py outputs and the application's RecompiledFuncs. Only the
two matrix conversion routines are replaced by observers; CPU pointer loads,
angle selection, armature traversal and Gfx emission execute production code.
All emulated memory accesses are checked before dereferencing host memory.
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def functions(text):
    return dict(re.findall(r"RECOMP_FUNC void (\w+)\([^\n]+\{(.*?)(?=\nRECOMP_FUNC|\Z)", text, re.S))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", type=Path, default=ROOT / "build/amped_up/offline_model_mod.c")
    parser.add_argument("--segment", type=Path, default=ROOT / "build/amped_up/amped_up_custom_segment.bin")
    parser.add_argument("--first-person", action="store_true", help="execute the compiled first-person limb/skin emission patch")
    args = parser.parse_args()
    mod = functions(args.offline.read_text())
    helper = next(name for name, body in mod.items() if "0X5400" in body and "0XC0" in body)
    selected = {helper: mod[helper]}
    pending = [helper]
    while pending:
        for name in re.findall(r"\b(mod_func_\d+)\(rdram, ctx\)", selected[pending.pop()]):
            if name not in selected:
                selected[name] = mod[name]
                pending.append(name)
    stock_names = {"render_animated_model", "render_armature", "render_limb_or_add_mtx",
                   "segmented_to_virtual", "adjust_angle"}
    for path in (ROOT / "RecompiledFuncs").glob("funcs_*.c"):
        selected.update({name: body for name, body in functions(path.read_text()).items() if name in stock_names})
    assert stock_names <= selected.keys()
    patch_symbols = {}
    if args.first_person:
        patch = functions((ROOT / "RecompiledPatches/patches.c").read_text())
        selected["render_limb_or_add_mtx"] = patch["render_limb_or_add_mtx"]
        pending = ["render_limb_or_add_mtx"]
        while pending:
            for name in re.findall(r"\b(\w+)\(rdram, ctx\)", selected[pending.pop()]):
                if name in patch and name not in selected:
                    selected[name] = patch[name]
                    pending.append(name)
        for line in (ROOT / "patches/patches.map").read_text().splitlines():
            fields=line.split()
            if len(fields)==5 and fields[-1] in ("mk64_vr_interaction","mk64_vr_local_draw"):
                patch_symbols[fields[-1]]=int(fields[0],16)
        assert len(patch_symbols)==2
    # All imported animation operands must select segment zero. A zeroed host
    # fixture must not accidentally hide a KSEG token indexing segment 128.
    selected["segmented_to_virtual"] = '\nassert((uint32_t)ctx->r4 >> 24 == 0);\n' + selected["segmented_to_virtual"]
    selected["render_animated_model"] = '\nlast_animation = (uint16_t)ctx->r6;\n' + selected["render_animated_model"]
    declarations = "\n".join(f"void {name}(uint8_t*, recomp_context*);" for name in selected)
    source = r'''
#include "recomp.h"
#include <stdio.h>
#include <string.h>
#undef RECOMP_FUNC
#define RECOMP_FUNC
static unsigned calls, cases, last_animation;
void recomp_vr_is_active(uint8_t* rdram,recomp_context* ctx){ctx->r2=1;}
static void* checked(uint8_t* ram, gpr address, unsigned size, unsigned swap) {
    if (address < 0xffffffff80000000ULL || address + size > 0xffffffff82000000ULL) {
        fprintf(stderr, "invalid CPU access: %016llx size=%u case=%u\n",
                (unsigned long long)address, size, cases);
        exit(2);
    }
    return ram + ((address - 0xffffffff80000000ULL) ^ swap);
}
#undef MEM_W
#undef MEM_H
#undef MEM_HU
#undef MEM_B
#undef MEM_BU
#define MEM_W(a,b) (*(int32_t*)checked(rdram,(a)+(b),4,0))
#define MEM_H(a,b) (*(int16_t*)checked(rdram,(a)+(b),2,2))
#define MEM_HU(a,b) (*(uint16_t*)checked(rdram,(a)+(b),2,2))
#define MEM_B(a,b) (*(int8_t*)checked(rdram,(a)+(b),1,3))
#define MEM_BU(a,b) (*(uint8_t*)checked(rdram,(a)+(b),1,3))
void mtxf_translate_rotate2(uint8_t* rdram, recomp_context* ctx) {
    for (int i=0; i<3; i++) (void)MEM_H(ctx->r6, i*2);
    calls++;
}
void convert_to_fixed_point_matrix_animation(uint8_t* rdram, recomp_context* ctx) {
    // The production caller computes the matrix destination; validate it too.
    checked(rdram, ctx->r4, 64, 0);
}
'''
    source += declarations + "\n"
    source += "\n".join(f"void {name}(uint8_t* rdram, recomp_context* ctx) {{{body}" for name, body in selected.items())
    source += r'''
// Compare inherited authored material/state across flattened first-person emission
// and the untouched source display-list traversal. Geometry/matrix tags are excluded.
static unsigned state_hash(uint8_t* rdram,unsigned start,unsigned end,unsigned hash,int depth) {
    assert(depth<20);
    for(unsigned address=start;address<end;address+=8) {
        unsigned w0=MEM_W(S32(address),0),w1=MEM_W(S32(address),4),op=w0>>24;
        if(op==0xb8)return hash;
        if(op==6) {
            unsigned target=0x80000000u|(w1&0xffffff);
            hash=state_hash(rdram,target,target+32768,hash,depth+1);
            if(w0&0x10000)return hash;
        } else if(op==0xb6 || op==0xb7 || op==0xbb || op==0xba || op==0xb9 ||
            op==0xfc || op==0xfd || op==0xf5 || op==0xf2 || op==0xf3 || op==0xf0 ||
            op==0xfb || op==0xfa || op==0xf8 || op==0xf9 || op==0xe6 || op==0xe7 ||
            op==0xe8 || op==0xdb || op==0xdc || op==0xbc || op==0x03) {
            hash=(hash^w0)*16777619u;hash=(hash^w1)*16777619u;
        }
    }
    return hash;
}
int main(int argc, char** argv) {
    uint8_t* rdram = calloc(1, 0x2000000);
    FILE* f = fopen(argv[1], "rb"); assert(f);
    for (unsigned i=0; i<0x32e3b0; i++) { int c=fgetc(f); assert(c>=0); rdram[(0x400000+i)^3]=c; }
    fclose(f);
    FP_INITIALIZE
    // Segment zero, production globals and an isolated display list / matrix pool.
    MEM_W(S32(0x80150258),0)=0;
    MEM_W(S32(0x8014ef40),0)=S32(0x80200000);
    unsigned effects[] = {0,0x200,0x80000,0x100000,0x4000000};
    for(int player=0;player<8;player++) for(int character=0;character<8;character++)
    for(int mode=0;mode<2;mode++) for(int effect=0;effect<5;effect++) for(int turnIndex=0;turnIndex<3;turnIndex++) {
        int turn = turnIndex==0 ? 0 : turnIndex==1 ? -1 : 1;
        recomp_context ctx={0};
        ctx.r29=S32(0x803f0000); ctx.r31=S32(0x80001234);
        ctx.r4=S32(0x800f6990+player*0xdd8);
        MEM_H(ctx.r4,0)=0x8000; MEM_H(ctx.r4,4)=0;
        MEM_W(ctx.r4,0xbc)=effects[effect]; MEM_H(ctx.r4,0xc0)=turn*0x1000;
        MEM_H(ctx.r4,0xca)=0;
        // LUI 800E plus signed C5A0/C510 addresses 800D, not 800E.
        // These are gCurrentCourseId and the D_800DC510 race/menu state.
        MEM_H(S32(0x800dc5a0),0)=mode?20:4;
        MEM_W(S32(0x800dc510),0)=4;
        MEM_H(ctx.r29,0x12)=character;
        MEM_H(S32(0x800f6990),0x254)=character;
        MEM_W(S32(0x80150298),0)=S32(0x80300000);
        MEM_W(S32(0x8018d120),0)=0;
        unsigned before=calls;
        HELPER(rdram,&ctx);
        assert(ctx.r29==S32(0x803f0000)); assert(ctx.r31==S32(0x80001234));
        assert(calls-before==9);
        if (mode) assert(last_animation == character + (player<3 ? 18 : 26));
        else if (effect==0 && turn==0) assert(last_animation == character+1);
        cases++;
    }
    // Independently traverse every animation entry for every armature. This
    // includes damage and podium entries beyond ordinary steering scenarios.
    for(int character=0;character<8;character++) for(int animation=0;animation<34;animation++) {
        recomp_context ctx={0}; ctx.r29=S32(0x803f0000); ctx.r31=S32(0x80001234);
        ctx.r4=MEM_W(S32(0x805a4740),character*4); ctx.r5=0x005a5400;
        ctx.r6=animation; ctx.r7=31;
        MEM_H(S32(0x800f6990),0x254)=character;
        MEM_W(S32(0x80150298),0)=S32(0x80300000); MEM_W(S32(0x8018d120),0)=0;
        unsigned before=calls; render_animated_model(rdram,&ctx); assert(calls-before==9);
        FP_VALIDATE
        cases++;
    }
    printf("PASS %u generated helper / stock traversal cases; %u animated limbs\n",cases,calls);
    free(rdram);
}
'''.replace("HELPER", helper)
    source=source.replace("FP_INITIALIZE", "") .replace("FP_VALIDATE", "") if not args.first_person else source.replace("FP_INITIALIZE", f"""
    MEM_W(S32(0x{patch_symbols['mk64_vr_local_draw']:08x}),0)=1;
    MEM_W(S32(0x{patch_symbols['mk64_vr_interaction']:08x}),4)=1;
    FILE* patchFile=fopen(argv[2],"rb"); assert(patchFile);
    for(unsigned i=0;;i++) {{int ch=fgetc(patchFile);if(ch<0)break;rdram[(0x801000+i)^3]=ch;}}
    fclose(patchFile);
""").replace("FP_VALIDATE", r"""
        unsigned seen=0, weights=0, vertices=0, anchors=0;
        const unsigned end=MEM_W(S32(0x80150298),0);
        for(unsigned address=0x80300000;address<end;address+=8){
            unsigned w0=MEM_W(S32(address),0),w1=MEM_W(S32(address),4);
            // Matrix-group extension embeds the explicit group id as its second word.
            if(w1==0x73000001u)anchors++;
            if((w1&0xff000000)==0x71000000){seen|=1u<<((w1>>12)&3);weights|=1u<<(w1&31);}
            if((w0>>24)==4){assert(((w0>>10)&63)==1);assert(((w0>>17)&127)<32);vertices++;}
        }
        assert(vertices>0 && (seen & 5)==5 && anchors==1);
        if(character==3)assert((weights&1) && (weights&0x80000000u));
        unsigned emittedState=state_hash(rdram,0x80300000,end,2166136261u,0);
        MEM_W(S32(FP_LOCAL_DRAW),0)=0;
        MEM_W(S32(0x80150298),0)=S32(0x80300000);MEM_W(S32(0x8018d120),0)=0;
        ctx=(recomp_context){0};ctx.r29=S32(0x803f0000);ctx.r31=S32(0x80001234);
        ctx.r4=MEM_W(S32(0x805a4740),character*4);ctx.r5=0x005a5400;ctx.r6=animation;ctx.r7=31;
        render_animated_model(rdram,&ctx);
        unsigned originalState=state_hash(rdram,0x80300000,MEM_W(S32(0x80150298),0),2166136261u,0);
        assert(emittedState==originalState);
        MEM_W(S32(FP_LOCAL_DRAW),0)=1;
""")
    if args.first_person:
        source=source.replace("FP_LOCAL_DRAW",f"0x{patch_symbols['mk64_vr_local_draw']:08x}u")
    with tempfile.TemporaryDirectory(prefix="amped-animation-") as directory:
        path = Path(directory)
        (path / "test.c").write_text(source)
        subprocess.run(["cc", "-std=c11", "-O1", "-w", "-I", str(ROOT / "lib/N64ModernRuntime/N64Recomp/include"),
                        str(path / "test.c"), "-o", str(path / "test")], check=True)
        subprocess.run([str(path / "test"), str(args.segment.resolve()),str(ROOT / "patches/patches.bin")], check=True)


if __name__ == "__main__":
    main()
