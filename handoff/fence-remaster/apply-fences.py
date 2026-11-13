"""Upscale indexed fence and railing textures, preserving alpha and index."""
import os
import shutil
import struct
import subprocess
import time
import zipfile
from pathlib import Path
import numpy as np

work=Path(__file__).resolve().parent
root=work.parents[1]
backup=work/'backups'
backup.mkdir(exist_ok=True)

def transform(data):
    w,h,bits=struct.unpack_from('<HHB',data,12)
    if data[0] or data[2]!=2 or (w,h)!=(128,128) or bits not in (24,32):
        raise ValueError('Unexpected input texture')
    channels=bits//8; end=18+w*h*channels
    temp=work/'checkpoint-source.tga'; temp.write_bytes(data)
    raw=subprocess.run(['ffmpeg','-v','error','-i',str(temp),'-vf','scale=256:256:flags=lanczos',
                        '-frames:v','1','-f','rawvideo','-pix_fmt','bgr24','pipe:1'],
                       check=True,stdout=subprocess.PIPE).stdout
    if len(raw)!=256*256*3: raise ValueError('Invalid image data')
    rgb=np.frombuffer(raw,np.uint8).reshape(256,256,3).astype(np.int16)
    centre=rgb[1:-1,1:-1]
    near=(rgb[:-2,1:-1]+rgb[2:,1:-1]+rgb[1:-1,:-2]+rgb[1:-1,2:])//4
    rgb[1:-1,1:-1]=np.clip(centre+np.clip((centre-near)*0.3,-8,8).astype(np.int16),0,255)
    rgb=rgb.astype(np.uint8)
    if channels==4:
        alpha=np.frombuffer(data,np.uint8,count=w*h*4,offset=18).reshape(h,w,4)[:,:,3]
        if not data[17]&32: alpha=alpha[::-1]
        alpha=np.repeat(np.repeat(alpha,2,axis=0),2,axis=1)
        rgb=np.concatenate((rgb,alpha[:,:,None]),axis=2)
    header=bytearray(data[:18]); struct.pack_into('<HH',header,12,256,256)
    if not header[17]&32: rgb=rgb[::-1]
    return bytes(header)+rgb.tobytes()+data[end:]

prepared=[]
for archive in sorted((root/'levels').glob('texture*.zip')):
    with zipfile.ZipFile(archive) as z:
        names=[n for n in z.namelist() if n.lower().endswith('.tga') and
               any(k in n.lower() for k in ('fence','rail','barrier','barr')) and
               struct.unpack_from('<HH',z.read(n),12)==(128,128)]
        if not names: continue
        if 'textures.dir' not in z.namelist():
            print('Skipped unindexed archive',archive.name)
            continue
        directory=bytearray(z.read('textures.dir')); wanted={n.lower():n for n in names}; found=set()
        for i in range(0,len(directory),64):
            key=bytes(directory[i:i+48]).split(b'\0',1)[0].decode('latin1').lower()
            if key in wanted:
                if struct.unpack_from('<II',directory,i+52)!=(128,128): raise ValueError(f'Bad index: {archive} {key}')
                struct.pack_into('<II',directory,i+52,256,256); found.add(wanted[key])
        if found!=set(names):
            print('Skipped unindexed textures:', archive.name, ', '.join(sorted(set(names)-found)))
        names=[name for name in names if name in found]
        if not names: continue
        original=backup/archive.name
        if original.exists(): raise FileExistsError(f'Backup exists: {original}')
        replacements={n:transform(z.read(n)) for n in names}; replacements['textures.dir']=bytes(directory)
        tmp=archive.with_suffix('.zip.new')
        with zipfile.ZipFile(tmp,'w') as out:
            for info in z.infolist(): out.writestr(info,replacements.get(info.filename,z.read(info)))
    with zipfile.ZipFile(tmp) as check:
        if check.testzip() is not None: raise ValueError(f'Invalid archive: {tmp}')
    prepared.append((archive,original,tmp,names))

for archive,original,tmp,names in prepared:
    shutil.copy2(archive,original)
    for attempt in range(6):
        try:
            os.replace(tmp,archive)
            break
        except PermissionError:
            if attempt == 5: raise
            time.sleep(0.5)
    print(archive.name,':',', '.join(names))
print('Updated',sum(len(names) for _,_,_,names in prepared),'textures in',len(prepared),'track archives')
