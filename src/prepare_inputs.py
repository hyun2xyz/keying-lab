"""Reproduce the accepted real camera inputs from locally downloaded originals."""
import argparse,hashlib,json,shutil,subprocess,zipfile
from pathlib import Path
from PIL import Image


def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--downloads',type=Path,required=True);p.add_argument('--shawl-zip',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();data=json.loads((root/'dataset_manifest.json').read_text(encoding='utf-8'))
    assert len(data['cases'])==8 and all(c['id']!='02_dance' for c in data['cases'])
    originals=root/'originals';originals.mkdir(exist_ok=True)
    for c in data['cases']:
        source=root/c['source_dir'];source.mkdir(parents=True,exist_ok=True)
        existing=sorted(source.glob('*.png'))
        if existing:
            assert len(existing)==96,'Partial source retained; resolve it before regenerating'
        elif c['id']=='01_hair_glasses':
            raise RuntimeError('Run src/fetch_tos_hair.py first to prepare the pinned CC BY EXRs.')
        elif c['id']=='04_sheer_shawl':
            assert sha(a.shawl_zip)==c['original_sha256'],'Original archive changed'
            with zipfile.ZipFile(a.shawl_zip) as bundle:
                for i,name in enumerate(c['selected_original_frames']):
                    with bundle.open(name) as stream:image=Image.open(stream).convert('RGB')
                    image.resize((1280,720),Image.Resampling.LANCZOS).save(source/f'{i:05}.png')
        else:
            original=originals/c['download_file']
            if not original.exists():shutil.copy2(a.downloads/c['download_file'],original)
            assert sha(original)==c['original_sha256'],'Downloaded version changed:'+c['download_file']
            subprocess.run(['ffmpeg','-v','error','-xerror','-n','-ss',str(c['start_seconds']),'-i',str(original),
                '-map','0:v:0','-vf',c['conversion_command'],'-frames:v','96','-start_number','0',str(source/'%05d.png')],check=True)
        for row in c['hashes']:
            frame=source/f'{row["frame"]:05}.png'
            assert sha(frame)==row['source_sha256'],str(frame)
            with Image.open(frame) as image:image.load();assert image.mode=='RGB' and image.size==(c['width'],c['height'])
        print('VERIFIED_REAL_INPUT',c['id'],96,flush=True)
    print('ACCEPTED_REAL_INPUTS_VERIFIED',768,flush=True)


if __name__=='__main__':main()
