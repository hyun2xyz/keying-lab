"""Fetch only the96 selected real TOS camera frames, CC BY3.0, with exact hashes."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

import numpy as np
from PIL import Image


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    root=parser.parse_args().root.resolve()
    data=json.loads((root/'docs/tos_hair_source.json').read_text(encoding='utf-8'))
    original=root/data['original_dir'];original.mkdir(parents=True,exist_ok=True)
    source=root/data['source_dir'];source.mkdir(parents=True,exist_ok=True)
    def fetch(row):
        name=row['original_name'];dest=original/name
        if not dest.exists():
            part=dest.with_suffix('.exr.part')
            with urllib.request.urlopen(data['source_url']+name,timeout=60) as response,part.open('wb') as out:
                while block:=response.read(1024*1024):out.write(block)
            assert sha(part)==row['original_sha256'],name
            part.replace(dest)
        assert sha(dest)==row['original_sha256'],name
        target=source/f'{row["frame"]:05}.png'
        if not target.exists():
            raw=subprocess.check_output(['ffmpeg','-v','error','-xerror','-i',str(dest),'-frames:v','1',
                '-f','rawvideo','-pix_fmt','gbrpf32le','-'])
            a=np.frombuffer(raw,dtype='<f4').reshape(3,1012,1920)[[2,0,1]].transpose(1,2,0)
            assert np.isfinite(a).all()
            rgb=np.where(a<=.0031308,12.92*np.maximum(a,0),1.055*np.maximum(a,0)**(1/2.4)-.055)
            Image.fromarray(np.round(np.clip(rgb,0,1)*255).astype(np.uint8)).save(target)
        assert sha(target)==row['source_sha256'],target.name
        return name
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i,name in enumerate(pool.map(fetch,data['hashes']),1):
            if i%12==0:print('VERIFIED',i,'/96',name,flush=True)
    (root/'samples/02_3c/source_manifest.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print('(CC) Blender Foundation | mango.blender.org | CC BY3.0',flush=True)


if __name__=='__main__':main()
