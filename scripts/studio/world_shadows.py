"""Render a camera-aligned shadow catcher from the actual world-space solids."""
import sys
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from world import create_camera

bpy.ops.wm.open_mainfile(filepath=str(ROOT/'assets/studio/world-studio.blend'))
scene=bpy.context.scene
for obj in list(scene.objects):
    if obj.type=='LIGHT' or obj.name.startswith(('Steam','FallingPetal','ScreenGlow','Setting_Paper')):
        bpy.data.objects.remove(obj,do_unlink=True)
    elif obj.type=='MESH':
        obj.visible_camera=False
        obj.visible_glossy=False
        obj.visible_transmission=False
        obj.visible_diffuse=False
        obj.visible_shadow=True
        if obj.name=='Setting_SolidTable':
            obj.visible_camera=True
            obj.is_shadow_catcher=True
            obj.data.materials.clear()
            material=bpy.data.materials.new('Shadow receiving tabletop')
            material.use_nodes=True
            shader=material.node_tree.nodes.get('Principled BSDF')
            shader.inputs['Base Color'].default_value=(1,1,1,1)
            shader.inputs['Roughness'].default_value=1
            obj.data.materials.append(material)
            for face in obj.data.polygons:face.material_index=0
        else:
            material=bpy.data.materials.get('Shadow solids') or bpy.data.materials.new('Shadow solids')
            material.use_nodes=True
            obj.data.materials.clear()
            obj.data.materials.append(material)
            for face in obj.data.polygons:face.material_index=0
world=bpy.data.worlds.new('Warm diffuse sky')
world.use_nodes=True
world.node_tree.nodes['Background'].inputs[0].default_value=(1,1,1,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.8
scene.world=world
light=bpy.data.lights.new('Soft upper-left sun','SUN')
light.energy=2.4
light.angle=.25
obj=bpy.data.objects.new('Soft upper-left sun',light)
scene.collection.objects.link(obj)
obj.rotation_euler=Vector((-.45,.25,-1)).to_track_quat('-Z','Y').to_euler()
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=24
scene.cycles.use_denoising=True
scene.render.film_transparent=True
scene.view_settings.view_transform='Standard'
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGBA'
scene.render.filepath=str(ROOT/'assets/studio/world-shadow-catcher.png')
bpy.ops.render.render(write_still=True)
