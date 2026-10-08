#!/usr/bin/env python3
"""Execute regenerated MIPS item patches and native spawn/update functions on host.
Terrain and audio services are inert; actor ownership, state, velocity, timers,
registration and destruction run the production code. Requires patch recompilation.
"""
from pathlib import Path
import re, subprocess, tempfile, tomllib, sys, argparse, hashlib
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/amped_up'))
from test_animation_runtime import functions
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rom',type=Path,required=True)
args=parser.parse_args()
assert hashlib.sha256(args.rom.read_bytes()).hexdigest()=='d6b8538dd63f0132ecb2856e7d32816ed3c30e3e479aecd23cf83fb6ba17a5da', 'supported US ROM required'
patch=functions((ROOT/'RecompiledPatches/patches.c').read_text())
allfunc=dict(patch)
for p in (ROOT/'RecompiledFuncs').glob('funcs_*.c'):
    for k,v in functions(p.read_text()).items():
        if k not in allfunc:allfunc[k]=v
native={'use_green_shell_item','use_red_shell_item','use_banana_item','add_actor_to_empty_slot','actor_init',
        'vec3f_copy_return','vec3s_copy','func_802B64C4','mtxf_translate_vec3f_mat3','copy_collision'}
roots=['mk64_vr_tick','mk64_vr_held_item','update_actor_green_shell','update_actor_red_blue_shell','update_actor_banana','destroy_actor','destroy_destructable_actor']
selected={k:allfunc[k] for k in roots};pending=list(selected)
while pending:
    for name in re.findall(r'\b(\w+)\(rdram, ctx\)',selected[pending.pop()]):
        if name not in selected and (name in native or name in patch):
            selected[name]=allfunc[name];pending.append(name)
external=set()
for body in selected.values():external.update(re.findall(r'\b(\w+)\(rdram, ctx\)',body))
external-=selected.keys()
symbols={s['name']:s['vram'] for section in tomllib.loads((ROOT/'MarioKart64RecompSyms/mk64.us.datasyms.toml').read_text())['section'] for s in section.get('symbols',[])}
for line in (ROOT/'patches/patches.map').read_text().splitlines():
    f=line.split()
    if len(f)==5 and f[-1] in ['held_index','held_type','held_local_valid','rear_red']:symbols[f[-1]]=int(f[0],16)
source=r'''
#include "recomp.h"
#include "mk64_first_person.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
#undef RECOMP_FUNC
#define RECOMP_FUNC
static Mk64VRInteraction command;
static int consumed, greenRegistered, redRegistered;
static const char *romPath,*patchPath;
void switch_error(const char* fn,uint32_t address,uint32_t table){fprintf(stderr,"bad switch %s %x %x\n",fn,address,table);abort();}
static void load(uint8_t* ram,const char* path,unsigned offset,unsigned address,unsigned count){
    FILE* f=fopen(path,"rb");assert(f);assert(!fseek(f,offset,SEEK_SET));
    for(unsigned i=0;i<count;i++){int ch=fgetc(f);if(ch<0){assert(count==0x200000);break;}ram[(address-0x80000000+i)^3]=ch;}
    fclose(f);
}
static void* checked(uint8_t* ram,gpr address,unsigned size,unsigned swap){
    if(!(address>=0xffffffff80000000ULL && address+size<=0xffffffff82000000ULL)){fprintf(stderr,"invalid memory %llx size=%u\n",(unsigned long long)address,size);abort();}
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
#define F(a,o) (*(float*)checked(rdram,S32(a)+(o),4,0))
'''
for k,v in symbols.items():
    if k in ['gPlayers','gPlayerOne','gControllers','gActorList','gNumActors','gGamestate','gActiveScreenMode','gDemoMode','gCourseTimer','gIsGamePaused','gCourseMinX','gCourseMinY','gCourseMinZ','gCourseMaxX','gCourseMaxY','gCourseMaxZ','gModeSelection','gPlayerPositionLUT','held_index','held_type','held_local_valid','rear_red']:
        source+=f'#define A_{k} 0x{v:08x}u\n'
stubs={
'recomp_vr_is_active':'ctx->r2=1;',
'recomp_mk64_vr_interaction':'memcpy(checked(rdram,ctx->r4,sizeof command,0),&command,sizeof command); command.command=0;',
'consume_item':'MEM_H(S32(A_gPlayers),0x10)=0;consumed++;',
'add_green_shell_in_unexpired_actor_list':'greenRegistered++;',
'add_red_shell_in_unexpired_actor_list':'redRegistered++;',
'sins':'ctx->f0.fl=(float)sin((int16_t)ctx->r4*6.283185307179586/65536.0);',
'coss':'ctx->f0.fl=(float)cos((int16_t)ctx->r4*6.283185307179586/65536.0);',
'sqrtf_recomp':'ctx->f0.fl=sqrtf(ctx->f12.fl);',
'calculate_surface_height':'ctx->f0.fl=-1000;',
}
for name in external:source+=f'void {name}(uint8_t* rdram,recomp_context* ctx){{{stubs.get(name,"ctx->r2=0;")}}}\n'
source+='\n'.join(f'void {name}(uint8_t*,recomp_context*);' for name in selected)
source+='\n'.join(f'void {name}(uint8_t* rdram,recomp_context* ctx){{{body}' for name,body in selected.items())
source+=r'''
static void call(uint8_t* rdram,void(*fn)(uint8_t*,recomp_context*),unsigned arg){
    recomp_context ctx={0};ctx.r29=S32(0x803f0000);ctx.r4=S32(arg);fn(rdram,&ctx);
}
static void init(uint8_t* rdram){
    memset(rdram,0,0x2000000);
    load(rdram,romPath,0x1000,0x80000400,0xf6510);
    load(rdram,romPath,0xf7510,0x8028df00,0x2c130);
    load(rdram,patchPath,0,0x80801000,0x200000);
    command=(Mk64VRInteraction){0};
    command.enabled=1;command.item_hand=1;command.hand_valid[1]=1;command.seat_height=6;command.world_scale=10;
    MEM_W(S32(A_held_index),0)=-1;MEM_W(S32(A_gGamestate),0)=4;F(A_gCourseTimer,0)=1;
    MEM_W(S32(A_gPlayerOne),0)=A_gPlayers;MEM_H(S32(A_gPlayers),0)=0x8000;
    F(A_gPlayers,0x70)=5.5;MEM_H(S32(A_gPlayers),0x1c)=0;
    MEM_H(S32(A_gCourseMinX),0)=MEM_H(S32(A_gCourseMinY),0)=MEM_H(S32(A_gCourseMinZ),0)=-10000;
    MEM_H(S32(A_gCourseMaxX),0)=MEM_H(S32(A_gCourseMaxY),0)=MEM_H(S32(A_gCourseMaxZ),0)=10000;
    consumed=greenRegistered=redRegistered=0;
}
int main(int argc,char** argv){
    assert(argc==3);romPath=argv[1];patchPath=argv[2];
    uint8_t* rdram=calloc(1,0x2000000);assert(rdram);
    for(int itemIndex=0;itemIndex<3;itemIndex++)for(int rear=0;rear<2;rear++)for(int quiet=0;quiet<2;quiet++){
        int item=itemIndex==0?1:itemIndex==1?3:5;
        init(rdram);MEM_H(S32(A_gPlayers),0x10)=item;command.command=1;
        call(rdram,mk64_vr_tick,0);assert(consumed==1);assert(MEM_H(S32(A_gActorList),6)==0);
        assert(MEM_W(S32(A_held_index),0)==0);
        command.command=2;command.rear=rear;command.velocity[2]=quiet?0:-3;
        call(rdram,mk64_vr_tick,0);
        assert(MEM_W(S32(A_held_index),0)==-1);
        assert(MEM_H(S32(A_gActorList),6)==(item==1?1:2));
        if(item==1 && (rear||quiet))assert(F(A_gActorList,0x2c)==0);
        if(item!=1)assert(fabs(F(A_gActorList,0x2c)-(rear?-8:quiet?.05f:3))<.001);
        assert(redRegistered==(item==5));assert(greenRegistered==(item==3));
        if(item==5){
            for(int tick=0;tick<(rear?35:30);tick++)call(rdram,update_actor_red_blue_shell,A_gActorList);
            if(rear){assert(MEM_H(S32(A_gActorList),6)==2);assert(!(MEM_HU(S32(A_gActorList),2)&0x1000));assert(F(A_gActorList,0x2c)==-8);}
            else assert(MEM_H(S32(A_gActorList),6)!=2); // native forward homing/path transition retained
        }
    }
    // Actual native attachment stays in seat coordinates through invalid samples,
    // translation and 90-degree kart turn. Zeroed invalid poses are not new targets.
    for(int item=1;item<=5;item+=2) {
        init(rdram);MEM_H(S32(A_gPlayers),0x10)=item;
        command.hand_pos[1][0]=2;command.hand_pos[1][1]=-1;command.hand_pos[1][2]=-3;
        command.command=1;call(rdram,mk64_vr_tick,0);
        assert(MEM_BU(S32(A_held_local_valid),0)==1);
        assert(fabs(F(A_gActorList,0x18)+2)<.001 && fabs(F(A_gActorList,0x1c)-5)<.001 && fabs(F(A_gActorList,0x20)-3)<.001);
        command.hand_valid[1]=0;memset(command.hand_pos,0,sizeof command.hand_pos);command.command=3;
        F(A_gPlayers,0x14)=100;F(A_gPlayers,0x18)=20;F(A_gPlayers,0x1c)=-50;
        MEM_H(S32(A_gPlayers),0x2e)=0x4000;
        call(rdram,mk64_vr_tick,0);
        assert(MEM_W(S32(A_held_index),0)==0 && MEM_H(S32(A_gActorList),6)==0);
        assert(fabs(F(A_gActorList,0x18)-97)<.001 && fabs(F(A_gActorList,0x1c)-25)<.001 && fabs(F(A_gActorList,0x20)+52)<.001);
        F(A_gPlayers,0x14)=200;call(rdram,mk64_vr_tick,0);
        assert(fabs(F(A_gActorList,0x18)-197)<.001 && MEM_H(S32(A_gActorList),6)==0);
        call(rdram,item==1?destroy_destructable_actor:destroy_actor,A_gActorList);
        assert(MEM_W(S32(A_held_index),0)==-1 && MEM_BU(S32(A_held_local_valid),0)==0);
        // Destructable banana first enters its native death animation; finish its
        // normal deallocation before requiring reuse of the exact same slot.
        if(item==1)call(rdram,destroy_actor,A_gActorList);
        // Reusing the exact slot/type must not resurrect an old local attachment.
        MEM_H(S32(A_gPlayers),0x10)=item;command.command=1;call(rdram,mk64_vr_tick,0);
        assert(MEM_BU(S32(A_held_local_valid),0)==1);
        // Invalid pending take uses this new native spawn point, then follows the kart.
        float freshX=F(A_gActorList,0x18),freshY=F(A_gActorList,0x1c),freshZ=F(A_gActorList,0x20);
        assert(fabs(freshX-197)>.01 || fabs(freshY-25)>.01 || fabs(freshZ+52)>.01);
        F(A_gPlayers,0x14)+=50;call(rdram,mk64_vr_tick,0);
        assert(fabs(F(A_gActorList,0x18)-freshX-50)<.001 && MEM_H(S32(A_gActorList),6)==0);
    }
    // The existing item button releases a tracked item through its real native
    // held-state handler, consuming the off edge and clearing VR ownership once.
    for(int item=1;item<=5;item+=2) {
        init(rdram);MEM_H(S32(A_gPlayers),0)=0xC000;
        MEM_H(S32(A_gPlayers),0x10)=item;command.command=1;call(rdram,mk64_vr_tick,0);
        MEM_H(S32(A_gControllers),8)=0x2000;
        call(rdram,item==1?update_actor_banana:item==3?update_actor_green_shell:update_actor_red_blue_shell,A_gActorList);
        assert(MEM_W(S32(A_held_index),0)==-1 && MEM_BU(S32(A_held_local_valid),0)==0);
        assert(MEM_H(S32(A_gActorList),6)==1 && !(MEM_HU(S32(A_gControllers),8)&0x2000));
        assert(consumed==1);
    }
    // Pause/cancel keeps the actor and does not launch; native destruction clears ownership
    // before even the same actor type/slot can be reused.
    init(rdram);MEM_H(S32(A_gPlayers),0x10)=3;command.command=1;call(rdram,mk64_vr_tick,0);
    command.command=3;call(rdram,mk64_vr_tick,0);assert(MEM_H(S32(A_gActorList),6)==0);
    call(rdram,destroy_actor,A_gActorList);assert(MEM_W(S32(A_held_index),0)==-1);
    MEM_H(S32(A_gActorList),0)=7;MEM_H(S32(A_gActorList),2)=0xD000;MEM_H(S32(A_gActorList),6)=0;
    assert(MEM_W(S32(A_held_index),0)==-1);
    puts("PASS native MIPS item spawn/consume/registration, quiet/forward/rear release, red post-30-tick behavior, cancellation, invalid-tracking moving/turning attachment, conventional item release and destruction cache ownership");
    free(rdram);
}
'''
with tempfile.TemporaryDirectory(prefix='mk64-native-items-') as d:
    p=Path(d);(p/'test.c').write_text(source)
    subprocess.run(['cc','-O1','-w','-I',str(ROOT/'include'),'-I',str(ROOT/'lib/N64ModernRuntime/N64Recomp/include'),str(p/'test.c'),'-lm','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test'),str(args.rom.resolve()),str(ROOT/'patches/patches.bin')],check=True)
