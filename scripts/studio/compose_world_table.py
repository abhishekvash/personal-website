"""Combine original wood grain with shadows cast by the reconstructed solids."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFilter

ROOT=Path(__file__).resolve().parents[2]
TEXTURES=ROOT/'public/scene/textures'

def compose():
    background=np.asarray(Image.open(TEXTURES/'background.png').convert('RGB')).copy()
    wood=np.asarray(Image.open(TEXTURES/'wood.png').convert('RGB'))
    mask_image=Image.new('L',(1536,1024))
    draw=ImageDraw.Draw(mask_image)
    draw.polygon([(230,770),(460,685),(1120,650),(1180,1024),(230,1024)],fill=255)
    draw.rectangle((1085,600,1535,885),fill=255)
    yy,xx=np.indices((1024,1536))
    mask=np.asarray(mask_image.filter(ImageFilter.GaussianBlur(18)),dtype=float)/255
    mask*=yy>801-.0807*xx
    clean=wood[yy%wood.shape[0],xx%wood.shape[1]]
    background=background*(1-mask[...,None])+clean*mask[...,None]
    shadow=np.asarray(Image.open(ROOT/'assets/studio/world-shadow-catcher.png').convert('RGBA'),dtype=float)[...,3]/255
    shade=1-shadow[...,None]*np.array([.78,.71,.58])
    Image.fromarray(np.clip(background*shade,0,255).astype('uint8')).save(TEXTURES/'world-table.png')
    print('Composed reference wood with world-space cast shadows.')

if __name__=='__main__':compose()
