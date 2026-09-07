"""Extend unobstructed source room materials onto real floor and wall surfaces."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'public/scene/textures'

def mirrored(source,box):
    a=np.asarray(source.crop(box).convert('RGB'))
    a=np.concatenate((a,a[:,::-1]),axis=1)
    return np.concatenate((a,a[::-1]),axis=0)

def wall_grain(source,box):
    """Retain source ink and grain without repeating broad painted lighting."""
    base=mirrored(source,box)
    height,width=base.shape[:2]
    # Blur periodic neighbors so lighting removal cannot introduce edge seams.
    repeated=Image.fromarray(np.tile(base,(3,3,1)))
    illumination=np.asarray(repeated.filter(ImageFilter.GaussianBlur(4)),dtype=float)
    illumination=illumination[height:2*height,width:2*width]
    return np.clip(base.astype(float)-illumination+base.mean(axis=(0,1)),0,255)

def prepare_room_walls(source=None):
    """Extend unobstructed wall grain without any original furniture pixels."""
    source=source or Image.open(ROOT/'landing page.png')
    samples={
        'Gaming':wall_grain(source,(793,311,815,328)),
        'Recording':wall_grain(source,(572,544,600,590)),
        'Workspace':wall_grain(source,(704,730,738,786)),
        'Kitchen':wall_grain(source,(982,706,999,735)),
    }
    yy,xx=np.indices((1024,1536))
    for room,base in samples.items():
        paint=base[yy%base.shape[0],xx%base.shape[1]].astype(float)
        # Sparse vertical panel joints follow wall distance. At two source
        # pixels per world unit, these remain fine ink lines in the home view.
        phase=(xx-100)%280
        joints=np.minimum(phase,280-phase)<1
        paint[joints]=paint[joints]*.74+np.array([28,61,91])*.26
        image=Image.fromarray(np.clip(paint,0,255).astype('uint8'))
        image.save(OUT/f'wall-{room}-rear.png')
        if room=='Workspace':
            # Separate ownership keeps the perpendicular wall's paint from
            # consuming texels belonging to the back wall during the bake.
            image.save(OUT/'wall-Workspace-right.png')
    print('Prepared clean room walls with source grain and sparse panel joints.')

def prepare_room_paint():
    from world_architecture_paint import prepare_architecture_paint
    prepare_architecture_paint()
    source=Image.open(ROOT/'landing page.png')
    pink=mirrored(source,(572,544,600,590))
    Image.fromarray(pink).save(OUT/'pink.png')
    gold=mirrored(source,(982,706,999,735))
    Image.fromarray(gold).save(OUT/'gold.png')
    floor_gold=mirrored(source,(730,904,744,912))
    floor_pink=mirrored(source,(666,634,698,650))
    yy,xx=np.indices((1024,1536))
    for room,base in [('Gaming',floor_pink),('Recording',floor_pink),('Workspace',floor_gold),('Kitchen',floor_gold)]:
        paint=base[yy%base.shape[0],xx%base.shape[1]].astype(float)
        # Tile divisions follow world distance, so the same floor remains
        # consistent when seen from the side. Its grain comes from the artwork.
        lines=(np.minimum(xx%100,100-xx%100)<1)|(np.minimum(yy%90,90-yy%90)<1)
        paint[lines]=paint[lines]*.63+np.array([28,61,91])*.37
        Image.fromarray(np.clip(paint,0,255).astype('uint8')).save(OUT/f'floor-{room}.png')
    prepare_room_walls(source)
    print('Prepared clean source-grain room floors and unobstructed pink paint.')

if __name__=='__main__':prepare_room_paint()
