"""Extract unchanged artwork pixels and clean material samples from the reference."""

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "public/scene"
TEXTURES = OUT / "textures"


def prepare():
    TEXTURES.mkdir(parents=True, exist_ok=True)
    source = Image.open(ROOT / "landing page.png").convert("RGB")
    if source.size != (1536, 1024):
        raise ValueError("The scene is calibrated to the original 1536 × 1024 image.")
    shutil.copyfile(ROOT / "landing page.png", OUT / "reference.png")
    samples = {
        "paper": (34, 65, 290, 321),
        "blue": (341, 685, 366, 714),
        "cream": (499, 322, 526, 344),
        "gold": (1000, 708, 1024, 744),
        "pink": (581, 539, 611, 575),
        "wood": (60, 865, 285, 1000),
        "bark": (1288, 521, 1320, 559),
        "ink": (712, 142, 723, 159),
    }
    for name, box in samples.items():
        crop = source.crop(box)
        # Mirrored tiles preserve the sampled paint texture without hard seams.
        tile = Image.new("RGB", (crop.width * 2, crop.height * 2))
        tile.paste(crop, (0, 0))
        tile.paste(crop.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (crop.width, 0))
        tile.paste(tile.crop((0, 0, tile.width, crop.height)).transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, crop.height))
        tile.save(TEXTURES / f"{name}.png")

    background = source.copy()
    remove = Image.new("L", source.size)
    draw = ImageDraw.Draw(remove)
    draw.polygon([(300,839),(309,826),(320,816),(325,600),(355,581),(356,430),(386,413),(389,265),(495,247),(532,221),(532,165),(563,163),(568,220),(582,230),(581,140),(615,75),(678,36),(717,24),(779,25),(830,55),(862,100),(875,191),(913,192),(921,242),(1026,266),(1031,445),(1080,461),(1085,632),(1110,639),(1107,850),(1125,861),(1128,884),(1123,895),(1100,903),(1098,926),(1089,931),(1064,929),(1063,923),(859,942),(856,948),(834,950),(830,948),(638,975),(616,976),(590,972),(489,982),(478,980),(473,992),(463,996),(445,993),(437,988),(424,988),(418,975),(407,971),(368,937),(324,895),(321,879),(300,853)], fill=255)
    draw.polygon([(928,0),(1536,0),(1536,590),(1450,595),(1481,627),(1481,668),(1467,770),(1447,802),(1390,825),(1304,830),(1200,815),(1160,803),(1140,765),(1137,672),(1145,622),(1180,603),(1256,590),(1215,510),(1120,508),(993,476),(974,361),(941,218)], fill=255)
    # The hidden background contains paper and table, never another copy of the objects.
    paper = np.asarray(Image.open(TEXTURES / "paper.png"))
    wood = np.asarray(Image.open(TEXTURES / "wood.png"))
    clean = np.asarray(background).copy()
    mask = np.asarray(remove) > 0
    yy, xx = np.indices(mask.shape)
    tabletop = yy > 801 - .0807 * xx
    clean[mask & ~tabletop] = paper[yy[mask & ~tabletop] % paper.shape[0], xx[mask & ~tabletop] % paper.shape[1]]
    clean[mask & tabletop] = wood[yy[mask & tabletop] % wood.shape[0], xx[mask & tabletop] % wood.shape[1]]
    Image.fromarray(clean).save(TEXTURES / "background.png")
    paper_background=clean.copy()
    remove_table_edge=yy>794-.0807*xx
    paper_background[remove_table_edge]=paper[yy[remove_table_edge]%paper.shape[0],xx[remove_table_edge]%paper.shape[1]]
    Image.fromarray(paper_background).save(TEXTURES / "paper-background.png")
    artwork = np.asarray(source).copy()
    steam_regions = [(839,688,884,772),(934,694,971,741)]
    motion = []
    for index,(x0,y0,x1,y1) in enumerate(steam_regions):
        patch=np.asarray(source,dtype=float)[y0:y1,x0:x1]
        # Interpolate the surrounding wall across the occluded plume. Preserve
        # the source plume itself as a separate straight-alpha paint layer.
        left=np.asarray(source,dtype=float)[y0:y1,x0-3:x0].mean(1)
        right=np.asarray(source,dtype=float)[y0:y1,x1:x1+3].mean(1)
        weight=np.linspace(0,1,x1-x0)[None,:,None]
        wall=left[:,None,:]*(1-weight)+right[:,None,:]*weight
        alpha=np.clip((patch[...,2]-wall[...,2])/(235-wall[...,2]),0,1)
        alpha *= ((patch[...,0]>216)&(patch[...,1]>177)&(patch[...,2]>127))
        active=alpha>.025
        foreground=np.clip((patch-wall*(1-alpha[...,None]))/np.maximum(alpha[...,None],.001),0,255)
        rgba=np.zeros((*alpha.shape,4),dtype=np.uint8)
        rgba[...,:3]=foreground.astype(np.uint8)
        rgba[...,3]=(alpha*255).astype(np.uint8)
        Image.fromarray(rgba).save(TEXTURES/f"steam-{index}.png")
        artwork[y0:y1,x0:x1][active]=wall[active].astype(np.uint8)
        motion.append({"name":f"Steam{index+1:02}","bounds":[x0,y0,x1,y1],"texture":f"steam-{index}"})
    Image.fromarray(artwork).save(TEXTURES/"artwork.png")
    (ROOT / "assets/studio").mkdir(parents=True, exist_ok=True)
    (ROOT / "assets/studio/material-samples.json").write_text(json.dumps(samples, indent=2) + "\n")
    (ROOT / "assets/studio/motion.json").write_text(json.dumps(motion,indent=2)+"\n")
    print("Prepared source artwork and eight material swatches.")


if __name__ == "__main__":
    prepare()
