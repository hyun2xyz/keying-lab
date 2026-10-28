"""Inspect an existing model matte over three backgrounds, without changing it."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--case',required=True);p.add_argument('--roi',nargs=4,type=int,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    data=json.loads((root/'dataset_manifest.json').read_text(encoding='utf-8'))
    c=next(c for c in data['cases'] if c['id']==a.case);x,y,w,h=a.roi
    assert 0<=x<x+w<=c['width'] and 0<=y<y+h<=c['height']
    frames=[0,24,46,47,48,49,50,72,95];canvas=Image.new('RGB',(1600,1840),'#171c20');draw=ImageDraw.Draw(canvas)
    draw.text((8,8),a.case+' / ROI '+str(a.roi)+' / '+c['credit']+' / no GT',fill='white')
    yy,xx=np.indices((c['height'],c['width']));bg=np.repeat((.34+.2*((xx//24+yy//24)%2))[...,None],3,axis=2)
    linear=lambda t:np.where(t<=.04045,t/12.92,((t+.055)/1.055)**2.4)
    srgb=lambda t:np.where(t<=.0031308,12.92*t,1.055*np.maximum(t,0)**(1/2.4)-.055)
    for row,i in enumerate(frames):
        name=f'{i:05}.png';rgba=np.array(Image.open(root/c['pred_rgba_dir']/name)).astype(np.float32)/255
        alpha=np.array(Image.open(root/'results'/a.case/'pred_alpha16'/name)).astype(np.float32)/65535
        pictures=[Image.open(root/c['source_dir']/name).convert('RGB'),Image.fromarray(np.round(alpha*255).astype(np.uint8)).convert('RGB')]
        for background in [bg,np.zeros_like(bg),np.ones_like(bg)]:
            rgb=srgb(linear(rgba[...,:3])*alpha[...,None]+linear(background)*(1-alpha[...,None]))
            pictures.append(Image.fromarray(np.round(np.clip(rgb,0,1)*255).astype(np.uint8)))
        for col,(label,image) in enumerate(zip(['SOURCE','MODEL ALPHA','GRAY CHECKER','BLACK','WHITE'],pictures)):
            draw.text((col*320+6,32+row*200),f'{label} / frame{i:02d}',fill='white')
            canvas.paste(image.crop((x,y,x+w,y+h)).resize((320,180),Image.Resampling.NEAREST),(col*320,50+row*200))
    a.output.parent.mkdir(exist_ok=True,parents=True);canvas.save(a.output,quality=95)
    print(a.output)


if __name__=='__main__':main()
