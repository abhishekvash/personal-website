"""One orthographic camera and orthogonal coordinate system for the whole scene."""
import math
import bpy
from mathutils import Matrix, Vector

AZIMUTH=math.radians(21)
ELEVATION=math.radians(13)
SCALE=1.0
ANCHOR=Vector((0,0,40))
IMAGE_ANCHOR=Vector((450,976,0))
RIGHT=Vector((math.cos(AZIMUTH),-math.sin(AZIMUTH),0))
UP=Vector((math.sin(AZIMUTH)*math.sin(ELEVATION),math.cos(AZIMUTH)*math.sin(ELEVATION),math.cos(ELEVATION)))
AWAY=UP.cross(RIGHT)
TARGET=ANCHOR+RIGHT*(768-IMAGE_ANCHOR.x)/SCALE+UP*(IMAGE_ANCHOR.y-512)/SCALE


def project(position):
    p=Vector(position)-ANCHOR
    return Vector((IMAGE_ANCHOR.x+SCALE*RIGHT.dot(p),IMAGE_ANCHOR.y-SCALE*UP.dot(p),SCALE*AWAY.dot(p)))


def unproject(position):
    u,v,depth=position
    return ANCHOR+RIGHT*(u-IMAGE_ANCHOR.x)/SCALE+UP*(IMAGE_ANCHOR.y-v)/SCALE+AWAY*depth/SCALE


def legacy_to_world(obj, depth_offset=0):
    matrix=obj.matrix_world.copy()
    for vertex in obj.data.vertices:
        p=matrix @ vertex.co
        vertex.co=unproject((p.x,1024-p.z,p.y+depth_offset))
    obj.matrix_world=Matrix.Identity(4)
    obj["coordinateSpace"]="world"
    obj.data.update()


def create_camera():
    data=bpy.data.cameras.new("ReferenceCamera")
    obj=bpy.data.objects.new("ReferenceCamera",data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location=TARGET-AWAY*3000
    obj.rotation_euler=(TARGET-obj.location).to_track_quat("-Z","Y").to_euler()
    data.type="ORTHO"
    data.ortho_scale=1536/SCALE
    data.clip_start=.1
    data.clip_end=10000
    scene=bpy.context.scene
    scene.camera=obj
    scene.render.resolution_x=1536
    scene.render.resolution_y=1024
    scene.render.resolution_percentage=100
    return obj


def metadata():
    return {"cameraTarget":[TARGET.x,TARGET.z,-TARGET.y],"horizontalLimitDegrees":8,"verticalLimitDegrees":4,"sourceSize":[1536,1024]}
