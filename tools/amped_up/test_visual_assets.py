#!/usr/bin/env python3
"""Validate the private emitted F3DEX graph, all eight palettes and source volume."""
import argparse, hashlib, struct
from pathlib import Path
from import_kart import BASE, MAGIC, CHARACTERS, build_extension, parse_dae, png_rgb

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kart-source',type=Path,required=True);args=p.parse_args()
b,report=build_extension(args.kart_source)
magic,version,flags,end,*roots=struct.unpack_from('>12I',b)
assert (magic,version,flags)==(MAGIC,1,3) and end==BASE+len(b)<=0x80800000
assert report['source_triangles']==6370 and report['triangles']==6014
assert len(report['parts'])==9 and 'steeringwheel' not in report['parts']
assert len(set(roots))==8
assert report['textures']['tyre.png']['n64_size']==[32,64]
assert report['seat_bounds'][1][1]<-.2 # no imported hull over the seated eye
geometry=[]; palettes=[]
for character,root in enumerate(roots):
    cache={};drawn=[];images=[];loads=[]
    def read(address,size):
        offset=(address|0x80000000)-BASE
        assert offset>=48 and offset+size<=len(b),f'out of payload {address:x}'
        return b[offset:offset+size]
    def walk(address,depth=0):
        assert depth<=2
        for i in range(10000):
            w0,w1=struct.unpack('>II',read(address+i*8,8));op=w0>>24
            if op==0xb8:return
            if op==0x06:walk(w1,depth+1)
            elif op==4:
                count=(w0>>10)&63;first=(w0>>17)&127;assert count<=32 and first+count<=32
                data=read(w1,count*16)
                for j in range(count):cache[first+j]=struct.unpack_from('>hhhHhhBBBB',data,j*16)
            elif op in (0xbf,0xb1):
                for word in ((w0,w1) if op==0xb1 else (w1,)):
                    drawn.append(tuple(cache[((word>>shift)&255)//2] for shift in (16,8,0)))
            elif op==0xfd:images.append(w1)
            elif op==0xf3:
                count=((w1>>12)&0xfff)+1
                tex=read(images[-1],count*2);loads.append(hashlib.sha256(tex).hexdigest())
                assert count<=2048
        raise AssertionError('unterminated emitted graph')
    walk(root)
    assert len(drawn)==6014
    # UVs, native vertex coordinates and shade widths are identical across all colors.
    geometry.append(hashlib.sha256(repr(drawn).encode()).hexdigest());palettes.append(loads)
    assert len(set(loads))>=5
assert len(set(geometry))==1
assert len({tuple(p) for p in palettes})==8
# The no-kart option still provides the Amped items and cannot activate a cockpit.
fallback,metadata=build_extension(None)
assert struct.unpack_from('>12I',fallback)==(MAGIC,1,1,BASE+48,*([0]*8))
print(f'PASS private graph: all 8 palettes, {report["triangles"]} triangles each, shared geometry {geometry[0]}, {len(b)} bytes; missing-kart fallback')
