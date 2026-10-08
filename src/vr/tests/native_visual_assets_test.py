#!/usr/bin/env python3
"""Execute generated MIPS visual hooks. Observe only visibility/matrix services;
asset gates, racer selection, graph filtering, GBI state and colors are production.
"""
from pathlib import Path
import re,subprocess,tempfile,tomllib,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/amped_up'))
from test_animation_runtime import functions
patch=functions((ROOT/'RecompiledPatches/patches.c').read_text());allfunc=dict(patch)
for path in (ROOT/'RecompiledFuncs').glob('funcs_*.c'):
    for k,v in functions(path.read_text()).items():allfunc.setdefault(k,v)
roots=['mk64_vr_finish_kart','mk64_vr_render_item']
stubs={
'recomp_vr_is_active':'ctx->r2=active;',
'mk64_vr_item_is_held':'ctx->r2=held;',
'is_within_render_distance':'ctx->f0.fl=distanceValue;',
'actor_rendered':'rendered++;','actor_not_rendered':'culled++;',
'func_802979F8':'shadow++;',
'render_set_position':'for(int i=0;i<16;i++)observed[i]=*(float*)checked(rdram,ctx->r4+i*4,4,0);ctx->r2=1;',
'convert_to_fixed_point_matrix_animation':'',
'sins':'ctx->f0.fl=(float)sin((int16_t)ctx->r4*6.283185307179586/65536.);',
'coss':'ctx->f0.fl=(float)cos((int16_t)ctx->r4*6.283185307179586/65536.);',
'segmented_to_virtual':'ctx->r2=S32((uint32_t)ctx->r4|0x80000000);',
}
selected={};todo=list(roots)
while todo:
    name=todo.pop()
    if name in selected or name in stubs:continue
    assert name in allfunc,name
    selected[name]=allfunc[name]
    todo+=re.findall(r'\b(\w+)\(rdram, ctx\)',selected[name])
symbols={s['name']:s['vram'] for sec in tomllib.loads((ROOT/'MarioKart64RecompSyms/mk64.us.datasyms.toml').read_text())['section'] for s in sec.get('symbols',[])}
for line in (ROOT/'patches/patches.map').read_text().splitlines():
    f=line.split()
    if len(f)==5 and f[-1] in ['mk64_vr_interaction','mk64_vr_local_draw']:symbols[f[-1]]=int(f[0],16)
source=r'''
#include "recomp.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
#undef RECOMP_FUNC
#define RECOMP_FUNC
static int active=1,held,rendered,culled,shadow;
static float distanceValue=100,observed[16];
static void* checked(uint8_t* ram,gpr address,unsigned size,unsigned swap){
 if(!(address>=0xffffffff80000000ULL && address+size<=0xffffffff82000000ULL)){fprintf(stderr,"invalid access %llx size=%u\n",(unsigned long long)address,size);abort();}
 return ram+((address-0xffffffff80000000ULL)^swap);
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
#define W(a,o) MEM_W(S32(a),o)
#define H(a,o) MEM_H(S32(a),o)
#define F(a,o) (*(float*)checked(rdram,S32(a)+(o),4,0))
static void load(uint8_t* rdram,const char* path,unsigned address){
 FILE* f=fopen(path,"rb");assert(f);int v;unsigned i=0;
 while((v=fgetc(f))!=EOF)rdram[((address-0x80000000)+i++)^3]=v;fclose(f);
}
'''
for k in ['gDisplayListHead','gPlayers','gPlayerOne','gCourseMaxY','gCourseMinY','mk64_vr_interaction','mk64_vr_local_draw','camera1']:
    source+=f'#define A_{k} 0x{symbols[k]:08x}u\n'
for name in selected:source+=f'void {name}(uint8_t*,recomp_context*);\n'
for name,body in stubs.items():source+=f'void {name}(uint8_t* rdram,recomp_context* ctx){{{body}}}\n'
source+='\n'.join(f'void {name}(uint8_t* rdram,recomp_context* ctx){{{body}' for name,body in selected.items())
state_source=(ROOT/'tools/amped_up/test_animation_runtime.py').read_text()
source+=state_source[state_source.index('static unsigned state_hash('):state_source.index('int main(int argc, char** argv)')]
source+=r'''
static void call(uint8_t* ram,void(*fn)(uint8_t*,recomp_context*),unsigned a,unsigned b){
 recomp_context c={0};c.r29=S32(0x81f00000);c.r4=S32(a);c.r5=S32(b);fn(ram,&c);
}
static int has(uint8_t* rdram,unsigned word){
 for(unsigned p=0x80300000;p<(unsigned)W(A_gDisplayListHead,0);p+=4)if((unsigned)W(p,0)==word)return 1;return 0;
}
int main(int argc,char**argv){
 assert(argc==3);uint8_t* rdram=calloc(1,0x2000000);
 load(rdram,argv[1],0x80801000);load(rdram,argv[2],0x80400000);
 W(A_gPlayerOne,0)=A_gPlayers;W(A_camera1,0)=0x80390000;
 H(A_gCourseMinY,0)=-1000;H(A_gCourseMaxY,0)=1000;
 const unsigned actor=0x80380000,start=0x80300000,assets=0x8072e3b0;
 for(int type=6;type<=8;type++)for(int holding=0;holding<2;holding++) {
  memset(checked(rdram,S32(actor),0x70,0),0,0x70);H(actor,0)=type;held=holding;
  F(actor,0x18)=10;F(actor,0x1c)=20;F(actor,0x20)=30;
  W(A_gDisplayListHead,0)=start;rendered=shadow=0;
  call(rdram,mk64_vr_render_item,0x80390000,actor);
  assert(rendered==1 && shadow==(!holding && type!=6));
  assert(fabsf(observed[0]-(type==6?.08f:.1f))<1e-6f);
  assert(observed[12]==10 && observed[13]==(type==6?18:20) && observed[14]==30);
  if(type==6)assert(has(rdram,0x004c8818)&&has(rdram,0x004c7ed0));
  else assert(has(rdram,0x004c9158)&&has(rdram,0x004c8c48)&&has(rdram,0x004c8ab8)&&has(rdram,type==7?0x0fbe32ff:0xf02314ff));
  assert(has(rdram,holding?(type==6?0x74000002:0x74000001):0x76380000));
  assert(H(actor,0)==type && H(actor,6)==0); // visual import never changes simulation
 }
 // Missing descriptor, inactive VR and the unverified blue shell never override retail.
 for(int mode=0;mode<3;mode++) {
  active=mode!=0;W(assets,0)=mode==1?0:0x4d4b5652;H(actor,0)=mode==2?42:7;
  W(A_gDisplayListHead,0)=start;call(rdram,mk64_vr_render_item,0x80390000,actor);
  assert((unsigned)W(A_gDisplayListHead,0)==start);
 }
 active=1;W(assets,0)=0x4d4b5652;
 H(actor,0)=7;distanceValue=-1;culled=0;W(A_gDisplayListHead,0)=start;
 call(rdram,mk64_vr_render_item,0x80390000,actor);assert(culled==1 && (unsigned)W(A_gDisplayListHead,0)==start);
 // Corrupt descriptors must never suppress the prior kart or render item roots.
 for(int field=0;field<3;field++) {
  unsigned saved=W(assets,field==0?4:12);
  W(assets,field==0?4:12)=field==0?2:(field==1?0x8072e3b0:0x80800008);
  W(A_gDisplayListHead,0)=start;call(rdram,mk64_vr_render_item,0x80390000,actor);
  assert((unsigned)W(A_gDisplayListHead,0)==start);
  W(assets,field==0?4:12)=saved;
 }
 for(int character=0;character<8;character++)for(int mode=0;mode<4;mode++) {
  H(A_gPlayers,0x254)=character;
  W(A_mk64_vr_local_draw,0)=mode!=1;W(A_mk64_vr_interaction,4)=mode!=2;
  W(assets,8)=mode==3?1:3;
  W(start,0)=0x06000000;W(start,4)=0x005aadf0;
  W(start,8)=0x0400040f;W(start,12)=0x00111110; // already emitted arm vertex
  W(A_gDisplayListHead,0)=start+16;
  unsigned original_state=state_hash(rdram,start,start+16,2166136261u,0);
  call(rdram,mk64_vr_finish_kart,start,0);
  if(mode)assert((unsigned)W(A_gDisplayListHead,0)==start+16 && has(rdram,0x005aadf0));
  else {
   unsigned before_cockpit=start;
   while((unsigned)W(before_cockpit,4)!=0x75000000) {before_cockpit+=8;assert(before_cockpit<(unsigned)W(A_gDisplayListHead,0));}
   assert(original_state==state_hash(rdram,start,before_cockpit,2166136261u,0));
   assert(!has(rdram,0x005aadf0));assert(has(rdram,0x00111110));
   if(!has(rdram,W(assets,16+character*4))){fprintf(stderr,"character %d root %08x end %08x\n",character,W(assets,16+character*4),W(A_gDisplayListHead,0));for(unsigned q=start;q<(unsigned)W(A_gDisplayListHead,0);q+=8)fprintf(stderr,"%08x %08x\n",W(q,0),W(q,4));abort();}assert(has(rdram,0x75000000));
  }
 }
 // A corrupt selected root cannot hide the original cockpit.
 W(A_mk64_vr_local_draw,0)=1;W(A_mk64_vr_interaction,4)=1;W(assets,8)=3;
 H(A_gPlayers,0x254)=0;
 for(int bad=0;bad<3;bad++) {
  unsigned saved=W(assets,16);W(assets,16)=bad==2?0xfffffff8u:(bad?0x00800000:0);
  W(start,0)=0x06000000;W(start,4)=0x005aadf0;W(A_gDisplayListHead,0)=start+8;
  call(rdram,mk64_vr_finish_kart,start,0);
  assert((unsigned)W(A_gDisplayListHead,0)==start+8 && has(rdram,0x005aadf0));
  W(assets,16)=saved;
 }
 puts("PASS generated native visual hooks: item colors/scales/held tags/culling/fallback; local FP cockpit all 8 colors; chase/remote/missing-kart unchanged");
}
'''
with tempfile.TemporaryDirectory(prefix='mk64-visual-hooks-') as d:
    p=Path(d);(p/'test.c').write_text(source)
    subprocess.run(['cc','-std=c11','-O1','-w','-I',str(ROOT/'lib/N64ModernRuntime/N64Recomp/include'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test'),str(ROOT/'patches/patches.bin'),str(ROOT/'build/amped_up/amped_up_model.assets.bin')],check=True)
