#!/usr/bin/env python3
"""Private COLLADA -> F3DEX cockpit. No asset bytes are checked into the repository.
Source: fznmeatpopsicle, https://twitter.com/fznmeatpopsicle (credit required).
The nine retained mesh nodes preserve every authored polygon, normal and UV.
Only the separate steeringwheel node is omitted in favor of the approved VR rim.
"""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zlib

BASE = 0x8072E3B0
MAGIC = 0x4D4B5652
CHARACTERS = ('mario','luigi','yoshi','toad','dk','wario','peach','bowser')
NS = {'c':'http://www.collada.org/2005/11/COLLADASchema'}
CREDIT = 'Model made by fznmeatpopsicle — https://twitter.com/fznmeatpopsicle'


def png_rgb(path):
    data=path.read_bytes()
    if data[:8]!=b'\x89PNG\r\n\x1a\n': raise ValueError('not a PNG')
    w,h,depth,kind,compression,filtering,interlace=struct.unpack('>IIBBBBB',data[16:29])
    if (depth,kind,compression,filtering,interlace)!=(8,2,0,0,0):
        raise ValueError(f'{path}: expected noninterlaced RGB8 source texture')
    at=8; packed=b''
    while at<len(data):
        size=struct.unpack_from('>I',data,at)[0]; tag=data[at+4:at+8]
        if tag==b'IDAT':packed+=data[at+8:at+8+size]
        at+=size+12
    raw=zlib.decompress(packed); stride=w*3; rows=[]; previous=bytearray(stride)
    if len(raw)!=(stride+1)*h:raise ValueError('invalid PNG scanline length')
    for y in range(h):
        mode=raw[y*(stride+1)]; row=bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)])
        for x in range(stride):
            a=row[x-3] if x>=3 else 0; b=previous[x]; c=previous[x-3] if x>=3 else 0
            if mode==0:predict=0
            elif mode==1:predict=a
            elif mode==2:predict=b
            elif mode==3:predict=(a+b)//2
            elif mode==4:
                p=a+b-c; distances=(abs(p-a),abs(p-b),abs(p-c)); predict=(a,b,c)[distances.index(min(distances))]
            else:raise ValueError('invalid PNG filter')
            row[x]=(row[x]+predict)&255
        rows.append(row);previous=row
    return w,h,rows


def parse_dae(path):
    tree=ET.parse(path).getroot()
    if tree.findtext('c:asset/c:up_axis',namespaces=NS)!='Z_UP':raise ValueError('source must be Z_UP')
    if float(tree.find('c:asset/c:unit',NS).get('meter'))!=1:raise ValueError('source must use metres')
    images={x.get('id'):x.findtext('c:init_from',namespaces=NS) for x in tree.findall('c:library_images/c:image',NS)}
    effects={x.get('id'):images[x.findtext('.//c:surface/c:init_from',namespaces=NS)] for x in tree.findall('c:library_effects/c:effect',NS)}
    materials={x.get('id'):effects[x.find('c:instance_effect',NS).get('url')[1:]] for x in tree.findall('c:library_materials/c:material',NS)}
    geometries={x.get('id'):x for x in tree.findall('c:library_geometries/c:geometry',NS)}
    parts=[]
    for node in tree.findall('c:library_visual_scenes/c:visual_scene/c:node',NS):
        instance=node.find('c:instance_geometry',NS)
        if instance is None:continue
        matrix=list(map(float,node.findtext('c:matrix',namespaces=NS).split()))
        def transformed(v,direction=False):
            return tuple(sum(matrix[r*4+c]*v[c] for c in range(3))+(0 if direction else matrix[r*4+3]) for r in range(3))
        bindings={x.get('symbol'):materials[x.get('target')[1:]] for x in instance.findall('.//c:instance_material',NS)}
        mesh=geometries[instance.get('url')[1:]].find('c:mesh',NS)
        arrays={}
        for source in mesh.findall('c:source',NS):
            values=list(map(float,source.findtext('c:float_array',namespaces=NS).split()))
            stride=int(source.find('c:technique_common/c:accessor',NS).get('stride'))
            arrays[source.get('id')]=[values[i:i+stride] for i in range(0,len(values),stride)]
        vertices={x.get('id'):x.find('c:input',NS).get('source')[1:] for x in mesh.findall('c:vertices',NS)}
        for poly in mesh.findall('c:polylist',NS):
            inputs={x.get('semantic'):(int(x.get('offset')),x.get('source')[1:]) for x in poly.findall('c:input',NS)}
            if set(inputs)!={'VERTEX','NORMAL','TEXCOORD'}:raise ValueError('unsupported COLLADA vertex semantics')
            stride=max(v[0] for v in inputs.values())+1
            stream=list(map(int,poly.findtext('c:p',namespaces=NS).split())); cursor=0; triangles=[]
            for count in map(int,poly.findtext('c:vcount',namespaces=NS).split()):
                if count<3:raise ValueError('degenerate source polygon')
                polygon=[]
                for i in range(count):
                    values={}
                    for semantic,(offset,source) in inputs.items():
                        if semantic=='VERTEX':source=vertices[source]
                        values[semantic]=arrays[source][stream[cursor+i*stride+offset]]
                    polygon.append((transformed(values['VERTEX']),transformed(values['NORMAL'],True),tuple(values['TEXCOORD'])))
                cursor+=count*stride
                triangles.extend((polygon[0],polygon[i],polygon[i+1]) for i in range(1,count-1))
            if cursor!=len(stream):raise ValueError('COLLADA index stream mismatch')
            parts.append((node.get('name'),bindings[poly.get('material')],triangles))
    return parts


def build_extension(source: Path | None):
    blob=bytearray(48)
    def append(data):
        while len(blob)%8:blob.append(0)
        address=BASE+len(blob);blob.extend(data);return address & 0xffffff
    def commands(words):return b''.join(struct.pack('>II',*word) for word in words)
    roots=[0]*8; report={'credit':CREDIT,'cockpit':False,'items':True}
    if source is not None:
        all_parts=[parse_dae(source/f'pipeframe64_{name}.dae') for name in CHARACTERS]
        def geometry(parts):return [(name,triangles) for name,texture,triangles in parts]
        if any(geometry(parts)!=geometry(all_parts[0]) for parts in all_parts):raise ValueError('character geometry differs')
        # The grey ring excludes the hub/shaft. Match its authored X radius and
        # centre to the accepted 18 cm VR wheel, retaining a level whole kart.
        ring=[v[0] for name,texture,triangles in all_parts[0] if name=='steeringwheel' and texture=='grey_dark.png' for t in triangles for v in t]
        lo=[min(v[i] for v in ring) for i in range(3)]; hi=[max(v[i] for v in ring) for i in range(3)]
        centre=[(lo[i]+hi[i])/2 for i in range(3)]; size=.18/((hi[0]-lo[0])/2)
        if not 1<size<3:raise ValueError('unexpected authored wheel size')
        def point(v):return (size*(v[0]-centre[0]),size*(v[2]-centre[2])-.28,size*(v[1]-centre[1])-.28)
        textures={}; texture_reports={}
        for texture in sorted({texture for parts in all_parts for name,texture,tris in parts if name!='steeringwheel'}):
            if Path(texture).name!=texture:raise ValueError('texture path escapes supplied source')
            w,h,rows=png_rgb(source/texture)
            # RGBA16 32x64 fits TMEM exactly, preserving the tyre's authored tread
            # and UVs. Other original maps are constant 32x32 colour swatches.
            tw,th=(32,64) if texture=='tyre.png' else (32,32)
            pixels=[]
            for y in range(th):
                for x in range(tw):
                    # Area-filter the private map into N64's 4 KiB texture budget.
                    rgb=[0,0,0]; samples=0
                    for sy in range(y*h//th,(y+1)*h//th):
                        for sx in range(x*w//tw,(x+1)*w//tw):
                            for c in range(3):rgb[c]+=rows[sy][sx*3+c]
                            samples+=1
                    r,g,b=(round(c/samples) for c in rgb);pixels.append(((r>>3)<<11)|((g>>3)<<6)|((b>>3)<<1)|1)
            textures[texture]=(append(struct.pack('>'+str(len(pixels))+'H',*pixels)),tw,th)
            texture_reports[texture]={'source_sha256':hashlib.sha256((source/texture).read_bytes()).hexdigest(),'source_size':[w,h],'n64_size':[tw,th]}
        lists=[]; all_positions=[]; triangle_count=0
        light=(-.3,.85,.4); length=math.sqrt(sum(v*v for v in light));light=tuple(v/length for v in light)
        for name,texture,triangles in all_parts[0]:
            if name=='steeringwheel':lists.append(0);continue
            tw,th=textures[texture][1:]; words=[]; triangle_count+=len(triangles)
            for start in range(0,len(triangles),10):
                chunk=triangles[start:start+10]; packed=b''
                for triangle in chunk:
                    # Z-up -> Y-up swaps handedness. Reverse winding once.
                    for pos,normal,uv in (triangle[0],triangle[2],triangle[1]):
                        p=point(pos);all_positions.append(p)
                        n=(normal[0],normal[2],normal[1]);nl=math.sqrt(sum(v*v for v in n))
                        shade=round(255*(.55+.45*max(0,sum(n[i]*light[i] for i in range(3))/max(nl,1e-8))))
                        xyz=[round(v*1000) for v in p]
                        st=[round(uv[0]*(tw-1)*32),round((1-uv[1])*(th-1)*32)]
                        if any(abs(v)>32767 for v in xyz+st):raise ValueError('vertex overflows N64 format')
                        packed+=struct.pack('>hhhHhhBBBB',*xyz,0,*st,shade,shade,shade,255)
                count=len(chunk)*3; pointer=append(packed)
                words.append((0x04000000|(count<<10)|(count*16-1),pointer))
                def indices(i):return ((i*3*2)<<16)|((i*3+1)*2<<8)|((i*3+2)*2)
                for i in range(0,len(chunk),2):
                    words.append((0xB1000000|indices(i),indices(i+1)) if i+1<len(chunk) else (0xBF000000,indices(i)))
            words.append((0xB8000000,0));lists.append(append(commands(words)))
        for character,parts in enumerate(all_parts):
            words=[]
            for index,(name,texture,tris) in enumerate(parts):
                if name=='steeringwheel':continue
                ptr,w,h=textures[texture];line=w*2//8
                words.extend([(0xE7000000,0),(0xFD100000,ptr),(0xF5100000,0x07000000),
                    (0xE6000000,0),(0xF3000000,0x07000000|((w*h-1)<<12)|((2048+line-1)//line)),
                    (0xE7000000,0),(0xF5100000|(line<<9),(2<<18)|(2<<8)),
                    (0xF2000000,((w-1)*4<<12)|((h-1)*4)),(0x06000000,lists[index])])
            words.append((0xB8000000,0));roots[character]=append(commands(words))
        report.update(cockpit=True,triangles=triangle_count,source_triangles=sum(len(t) for _,_,t in all_parts[0]),
            parts=sorted({name for name,_,_ in all_parts[0] if name!='steeringwheel'}),
            source_wheel_centre=centre,scale=size,seat_bounds=[[min(v[i] for v in all_positions),max(v[i] for v in all_positions)] for i in range(3)],
            textures=texture_reports,roots=roots,
            sources={name:hashlib.sha256((source/f'pipeframe64_{name}.dae').read_bytes()).hexdigest() for name in CHARACTERS})
    while len(blob)%4:blob.append(0)
    if BASE+len(blob)>0x80800000:raise ValueError('private visual assets exceed reserved expansion RAM')
    struct.pack_into('>12I',blob,0,MAGIC,1,1|(2 if source else 0),BASE+len(blob),*roots)
    report.update(bytes=len(blob),end=f'0x{BASE+len(blob):08X}',sha256=hashlib.sha256(blob).hexdigest())
    return bytes(blob),report
