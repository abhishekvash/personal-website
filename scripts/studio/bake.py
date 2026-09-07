"""Bake reference-visible surface ownership into compact, padded texture atlases.

Only pixels visible on a particular mesh in the reference camera are copied.
Previously occluded regions receive clean material samples, not foreground art.
"""

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "assets/studio"
OUT = ROOT / "public/scene/textures"
WIDTH, HEIGHT = 1536, 1024


def bake():
    data = np.load(WORK / "projection.npz")
    triangles, owners, face_ids = data["triangles"], data["owners"], data["face_ids"]
    objects = json.loads((WORK / "projection.json").read_text())
    depth = np.full((HEIGHT, WIDTH), np.inf, dtype=np.float32)
    visible = np.full((HEIGHT, WIDTH), -1, dtype=np.int32)
    visible_face = np.full((HEIGHT, WIDTH), -1, dtype=np.int32)
    for triangle, owner, face_id in zip(triangles, owners, face_ids):
        x0 = max(0, int(math.floor(triangle[:, 0].min())))
        y0 = max(0, int(math.floor(triangle[:, 1].min())))
        x1 = min(WIDTH, int(math.ceil(triangle[:, 0].max())))
        y1 = min(HEIGHT, int(math.ceil(triangle[:, 1].max())))
        if x1 <= x0 or y1 <= y0:
            continue
        a, b, c = triangle
        denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(denominator) < 1e-7:
            continue
        yy, xx = np.ogrid[y0:y1, x0:x1]
        x, y = xx+.5, yy+.5
        w0 = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
        w1 = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
        w2 = 1-w0-w1
        z = w0*a[2]+w1*b[2]+w2*c[2]
        update = (w0 >= -1e-5) & (w1 >= -1e-5) & (w2 >= -1e-5) & (z < depth[y0:y1,x0:x1])
        depth[y0:y1,x0:x1][update] = z[update]
        visible[y0:y1,x0:x1][update] = owner
        visible_face[y0:y1,x0:x1][update] = face_id

    source = np.asarray(Image.open(OUT / "artwork.png").convert("RGB"))
    samples = {p.stem: np.asarray(Image.open(p).convert("RGB")) for p in OUT.glob("*.png") if p.stem in ("blue","cream","pink","gold","wood","bark","ink","paper")}
    patches = []
    mapping = {}
    for index, obj in enumerate(objects):
        if not obj["source"]:
            continue
        own = visible == index
        if not own.any():
            mapping[obj["name"]] = {"fill": obj["fill"], "object": obj["object"], "faces": obj["faces"]}
            continue
        x0, y0, x1, y1 = obj["bounds"]
        x0,y0 = max(0,int(math.floor(x0))-2),max(0,int(math.floor(y0))-2)
        x1,y1 = min(WIDTH,int(math.ceil(x1))+2),min(HEIGHT,int(math.ceil(y1))+2)
        if x1<=x0 or y1<=y0:
            mapping[obj["name"]] = {"fill":obj["fill"], "object": obj["object"], "faces": obj["faces"]}
            continue
        sample = samples.get(obj["fill"],samples["blue"])
        yy,xx = np.indices((y1-y0,x1-x0))
        patch = sample[(yy+y0)%sample.shape[0],(xx+x0)%sample.shape[1]].copy()
        mask = own[y0:y1,x0:x1].copy()
        patch[mask] = source[y0:y1,x0:x1][mask]
        # Bleed only an owned texel's color. Reading neighboring source pixels
        # here would paint foreground blossoms and ink onto hidden surfaces.
        for _ in range(2):
            expanded=mask.copy()
            for dy,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                donor=np.roll(mask,(dy,dx),(0,1))
                if dy<0: donor[dy:]=False
                if dy>0: donor[:dy]=False
                if dx<0: donor[:,dx:]=False
                if dx>0: donor[:,:dx]=False
                take=donor & ~expanded
                patch[take]=np.roll(patch,(dy,dx),(0,1))[take]
                expanded|=take
            mask=expanded
        padded = np.pad(patch,((3,3),(3,3),(0,0)),mode="edge")
        patches.append((obj["name"],padded,(x0,y0,x1,y1),np.unique(visible_face[own]).tolist()))
    patches.sort(key=lambda entry: entry[1].shape[0],reverse=True)
    atlas_size = 4096
    pages = []
    page = np.zeros((atlas_size,atlas_size,3),dtype=np.uint8)
    x=y=row_height=0
    for name,patch,bounds,visible_faces in patches:
        h,w = patch.shape[:2]
        if x+w>atlas_size:
            x=0
            y+=row_height
            row_height=0
        if y+h>atlas_size:
            pages.append(page)
            page=np.zeros((atlas_size,atlas_size,3),dtype=np.uint8)
            x=y=row_height=0
        page[y:y+h,x:x+w]=patch
        obj=next(obj for obj in objects if obj["name"]==name)
        mapping[name]={"page":len(pages),"origin":[x+3,y+3],"bounds":bounds,"visibleFaces":visible_faces,"object":obj["object"],"faces":obj["faces"],"fill":obj["fill"]}
        x+=w
        row_height=max(row_height,h)
    pages.append(page)
    for index,page in enumerate(pages):
        Image.fromarray(page).save(OUT/f"atlas-{index}.png",optimize=True)
    (WORK/"atlas.json").write_text(json.dumps({"size":atlas_size,"objects":mapping},ensure_ascii=False)+"\n")
    # Diagnostic proof of ownership, independent of the material's artwork.
    rgb = np.zeros((HEIGHT,WIDTH,3),dtype=np.uint8)
    valid=visible>=0
    for channel,multiplier in enumerate((71,137,211)):
        rgb[...,channel][valid]=(visible[valid]*multiplier+47)%255
    Image.fromarray(rgb).save(WORK/"surface-ownership.png")
    np.save(WORK/"visible-owners.npy",visible)
    print(f"Baked {len(patches)} visible mesh surfaces into {len(pages)} texture atlases.")


if __name__ == "__main__":
    bake()
