"""Reserve facade, roof, and side-wall artwork for their own physical surfaces."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'public/scene/textures'

def sample(name):
    a=np.asarray(Image.open(OUT/(name+'.png')).convert('RGB'))
    yy,xx=np.indices((1024,1536))
    return Image.fromarray(a[yy%a.shape[0],xx%a.shape[1]])

def prepare_architecture_paint():
    source=Image.open(ROOT/'landing page.png').convert('RGB')
    cream=sample('cream')
    mask=Image.new('L',source.size);draw=ImageDraw.Draw(mask)
    for poly in [
      [(594,324),(949,297),(970,471),(947,485),(603,515),(594,500)],
      [(504,515),(953,497),(971,519),(977,637),(960,651),(504,692),(487,672),(490,537)],
      [(495,739),(750,711),(765,887),(750,918),(479,946),(466,930),(473,758)],
      [(773,706),(1066,678),(1082,870),(1064,885),(793,914),(778,898)],
    ]: draw.polygon(poly,fill=255)
    draw.rounded_rectangle((512,363,582,489),radius=9,fill=255)
    draw.ellipse((998,521,1060,598),fill=255)
    Image.composite(cream,source,mask.filter(ImageFilter.GaussianBlur(.5))).save(OUT/'architecture-front.png')
    sides=source.copy()
    for box,crop in [((337,703,379,752),(338,681,350,701)),((367,741,428,835),(378,703,407,726)),((375,510,439,607),(379,475,405,503)),((408,326,462,419),(405,291,437,321))]:
        side_mask=Image.new('L',source.size);draw=ImageDraw.Draw(side_mask)
        draw.ellipse(box,fill=255)
        paint=np.asarray(source.crop(crop))
        paint=np.concatenate((paint,paint[:,::-1]),axis=1)
        paint=np.concatenate((paint,paint[::-1]),axis=0)
        yy,xx=np.indices((1024,1536))
        fill=Image.fromarray(paint[yy%paint.shape[0],xx%paint.shape[1]])
        sides=Image.composite(fill,sides,side_mask.filter(ImageFilter.GaussianBlur(.5)))
    sides.save(OUT/'architecture-sides.png')
    roof_mask=mask.copy();draw=ImageDraw.Draw(roof_mask)
    draw.polygon([(490,250),(526,235),(531,163),(569,162),(574,228),(582,224),(582,132),(615,63),(674,24),(775,21),(838,54),(879,127),(879,195),(919,192),(919,274),(885,282),(589,290),(493,290)],fill=255)
    Image.composite(cream,source,roof_mask.filter(ImageFilter.GaussianBlur(.5))).save(OUT/'architecture-roofs.png')
    right=Image.open(ROOT/'Codex Image Sep 7, 2026, 12_09_29 AM.png').convert('RGB')
    pixels=np.asarray(right,dtype=float)
    yy,xx=np.indices((1024,1536))
    pink=(pixels[:,:,0]>pixels[:,:,1]*1.3)&(pixels[:,:,2]>pixels[:,:,1]*.95)&(pixels[:,:,0]>140)
    pink&=(xx>880)&(xx<1040)&(yy>250)&(yy<650)
    clear=Image.fromarray((pink*255).astype('uint8')).filter(ImageFilter.MaxFilter(5))
    draw=ImageDraw.Draw(clear)
    for box in [(907,323,958,413),(934,518,987,611),(934,746,985,832),(975,708,1023,758)]:
        draw.ellipse(box,fill=255)
    patch=np.asarray(right.crop((942,283,966,307)))
    patch=np.concatenate((patch,patch[:,::-1]),axis=1)
    patch=np.concatenate((patch,patch[::-1]),axis=0)
    fill=Image.fromarray(patch[yy%patch.shape[0],xx%patch.shape[1]])
    Image.composite(fill,right,clear.filter(ImageFilter.GaussianBlur(.5))).save(OUT/'architecture-right.png')
    print('Separated facade, porthole, room, and roof source ownership.')

if __name__=='__main__':prepare_architecture_paint()
