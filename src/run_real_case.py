"""Run the external pinned CorridorKey engine on real footage, without invented GT."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

import numpy as np
from PIL import Image,ImageDraw


def linear(x):return np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
def srgb(x):return np.where(x<=.0031308,12.92*x,1.055*np.maximum(x,0)**(1/2.4)-.055)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--engine',required=True,type=Path)
    parser.add_argument('--cache',required=True,type=Path)
    parser.add_argument('--case',required=True)
    parser.add_argument('--progress-json',type=Path)
    args=parser.parse_args();root=args.root.resolve();engine=args.engine.resolve();cache=args.cache.resolve()
    manifest=json.loads((root/'dataset_manifest.json').read_text(encoding='utf-8'))
    case=next(c for c in manifest['cases'] if c['id']==args.case)
    source=root/case['source_dir'];result=root/'results'/case['id'];result.mkdir(parents=True,exist_ok=False)
    native=result/'native';width,height=case['width'],case['height']
    for row in case['hashes']:
        with (source/f'{row["frame"]:05}.png').open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['source_sha256']
    for key,folder in [('HF_HOME','huggingface'),('TORCH_HOME','torch'),('TEMP','tmp'),('TMP','tmp')]:
        path=cache/folder;path.mkdir(exist_ok=True,parents=True);os.environ[key]=str(path)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    log_path=result/'engine.log'
    def progress(phase,movie=None):
        if args.progress_json:
            d={'phase':phase,'sample':case['id']+' / '+case['title'],'source_dir':str(source),'fps':24,
               'message':'Real camera footage. Actual external CorridorKey 2.0, fixed low-VRAM24/12, no alpha hint. '+case['credit'],
               'logs':[str(log_path)],'recording_note':'Actual inference / completed result playback is labelled'}
            if movie:d['result_video']=str(movie)
            args.progress_json.write_text(json.dumps(d),encoding='utf-8')
    progress('ACTUAL CORRIDORKEY 2.0 / REAL CAMERA INPUT')
    sys.path.insert(0,str(engine))
    import torch
    assert torch.cuda.is_available();torch.cuda.reset_peak_memory_stats()
    start=time.perf_counter()
    sys.argv=[str(engine/'infer.py'),'--input',str(source),'--output_dir',str(native),
        '--frame_dir_fps','24','--temp_dir',str(cache/'inference-real5'/case['id']),
        '--low_vram','--hann_chunk','24','--hann_stride','12','--outputs','alpha','fg','checker','cutout']
    class Tee:
        def __init__(self,stream,file):self.stream=stream;self.file=file
        def write(self,text):self.stream.write(text);self.file.write(text);self.file.flush()
        def flush(self):self.stream.flush();self.file.flush()
    with log_path.open('w',encoding='utf-8') as log:
        with contextlib.redirect_stdout(Tee(sys.stdout,log)):
            print('ACTUAL_ENGINE_START',case['id'],flush=True)
            runpy.run_path(str(engine/'infer.py'),run_name='__main__')
    torch.cuda.synchronize();seconds=time.perf_counter()-start
    allocated=torch.cuda.max_memory_allocated()/1024**3;reserved=torch.cuda.max_memory_reserved()/1024**3
    cutout=native/'source_cutout.mov'
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
        'stream=width,height,pix_fmt,color_space,color_range,color_transfer,color_primaries,r_frame_rate','-of','json',str(cutout)],text=True))['streams'][0]
    assert (probe['width'],probe['height'])==(width,height) and probe['color_space']=='bt709'
    decode=['ffmpeg','-v','error','-xerror','-i',str(cutout),'-map','0:v:0','-vf',
        'scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgba64le','-f','rawvideo','-pix_fmt','rgba64le','-']
    decoder=subprocess.Popen(decode,stdout=subprocess.PIPE)
    rgba_dir=result/'pred_rgba';rgba_dir.mkdir();alpha_dir=result/'pred_alpha16';alpha_dir.mkdir()
    yy,xx=np.indices((height,width));checker=np.repeat((.34+.2*((xx//24+yy//24)%2))[...,None],3,axis=2).astype(np.float32)
    alpha_deltas=[];previous=None;probe_values=[]
    x,y,rw,rh=case['roi'];px,py,pw,ph=case['screen_probe']
    indices=[0,24,46,47,48,49,50,72,95]
    contact=Image.new('RGB',(1600,40+200*len(indices)),'#171c20');draw=ImageDraw.Draw(contact)
    draw.text((8,8),case['id']+' / consecutive native ROI, actual alpha / no GT / '+case['credit'],fill='white')
    for i in range(96):
        raw=decoder.stdout.read(width*height*8)
        assert len(raw)==width*height*8,(case['id'],i,len(raw))
        rgba16=np.frombuffer(raw,dtype='<u2').reshape(height,width,4)
        alpha=rgba16[...,3].astype(np.float32)/65535
        rgba8=np.round(rgba16.astype(np.float32)/257).astype(np.uint8)
        Image.fromarray(rgba8).save(rgba_dir/f'{i:05}.png')
        Image.fromarray(rgba16[...,3]).save(alpha_dir/f'{i:05}.png')
        probe_values.append(float(alpha[py:py+ph,px:px+pw].mean()))
        if previous is not None:alpha_deltas.append(float(np.mean(np.abs(alpha-previous))))
        previous=alpha.copy()
        if i in indices:
            row=indices.index(i);crop=(x,y,x+rw,y+rh)
            pieces=[Image.open(source/f'{i:05}.png').convert('RGB'),Image.fromarray(np.round(alpha*255).astype(np.uint8)).convert('RGB')]
            rgb=linear(rgba16[...,:3].astype(np.float32)/65535)
            for background in [checker,np.zeros_like(checker),np.ones_like(checker)]:
                comp=srgb(rgb*alpha[...,None]+linear(background)*(1-alpha[...,None]))
                pieces.append(Image.fromarray(np.round(np.clip(comp,0,1)*255).astype(np.uint8)))
            for col,(name,image) in enumerate(zip(['SOURCE','MODEL ALPHA','GRAY CHECKER','BLACK','WHITE'],pieces)):
                draw.text((col*320+6,32+row*200),f'{name} / frame{i:02}',fill='white')
                contact.paste(image.crop(crop).resize((320,180),Image.Resampling.NEAREST),(col*320,50+row*200))
        if i%24==0:print('REAL_OUTPUT_DECODED',case['id'],i+1,'/96',flush=True)
    assert not decoder.stdout.read(1);decoder.stdout.close();assert decoder.wait(timeout=60)==0
    metrics={'id':case['id'],'title':case['title'],'frames':96,'fps':24,'width':width,'height':height,
        'ground_truth_available':False,'accuracy_metrics':None,
        'screen_probe_xywh':case['screen_probe'],'screen_probe_mean_alpha':float(np.mean(probe_values)),
        'screen_probe_per_frame':probe_values,'mean_absolute_alpha_change':float(np.mean(alpha_deltas)),
        'interpretation':'Screen-probe alpha is a sampled background diagnostic. Alpha change includes real subject/camera motion; it is not a flicker score. No ground truth alpha or numerical accuracy claim.',
        'engine_seconds':round(seconds,3),'processing_fps':round(96/seconds,3),
        'peak_torch_allocated_GiB':round(allocated,3),'peak_torch_reserved_GiB':round(reserved,3),
        'profile':{'low_vram':True,'hann_chunk':24,'hann_stride':12,'hint':'none','despill':.5},
        'alpha_precision':'ProRes4444 with upstream alpha10 input, decoded to16-bit storage; not16-bit effective alpha. Same-host control max error49/65535.',
        'native_cutout_stream':probe,'decode_filter':decode[decode.index('-vf')+1]}
    (result/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    contact.save(root/'qa'/f'{case["id"]}_roi_review.jpg',quality=95)
    progress('COMPLETED REAL INFERENCE / RESULT PLAYBACK',native/'source_checker_comp_despill050.mp4')
    print('REAL_CASE_VALIDATED',case['id'],round(seconds,3),'seconds',flush=True)


if __name__=='__main__':main()
