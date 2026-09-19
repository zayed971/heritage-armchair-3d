"""Studio render. Usage: blender -b out/chair.blend -P render_chair.py -- <view> <out.png> [res] [samples]"""
import bpy, sys, math
from math import radians, sin, cos
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
argv = sys.argv[sys.argv.index("--") + 1:]
view, outp = argv[0], argv[1]
res = int(argv[2]) if len(argv) > 2 else 800
samples = int(argv[3]) if len(argv) > 3 else 40

VIEWS = {  # azimuth (0 = front, +ve toward chair's left), elevation, distance, target z, lens
    "hero":   (-32, 14, 3.1, 0.52, 70),
    "front":  (0, 8, 3.2, 0.53, 70),
    "side":   (-88, 8, 3.2, 0.53, 70),
    "back":   (-150, 12, 3.2, 0.53, 70),
    "high":   (-38, 38, 3.0, 0.48, 70),
    "detail_back": (-24, 4, 1.15, 0.93, 85),
    "detail_arm":  (-62, 24, 1.0, 0.66, 85),
    "detail_seat": (-20, 40, 1.2, 0.47, 85),
}
az, el, dist, tz, lens = VIEWS[view]
TARGETS = {"detail_back": (0.02, 0.36, 0.93), "detail_arm": (0.27, -0.12, 0.66), "detail_seat": (0.0, -0.05, 0.47)}
tgt = TARGETS.get(view, (0.0, 0.03, tz))

sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6
sc.cycles.diffuse_bounces = 3
sc.cycles.glossy_bounces = 4
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.03
sc.render.resolution_x = res
sc.render.resolution_y = int(res * 1.25)
sc.render.film_transparent = False
sc.view_settings.view_transform = "AgX"
try:
    sc.view_settings.look = "AgX - Medium High Contrast"
except Exception:
    pass
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = outp

# world: studio HDRI, dimmed, as fill + reflections
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
nt = w.node_tree; bg = nt.nodes["Background"]
env = nt.nodes.new("ShaderNodeTexEnvironment")
env.image = bpy.data.images.load(str(ROOT / "tex" / "hdri" / "hdri_photo_studio_01.hdr"))
mp = nt.nodes.new("ShaderNodeMapping"); tc = nt.nodes.new("ShaderNodeTexCoord")
mp.inputs["Rotation"].default_value = (0, 0, radians(110))
nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
nt.links.new(env.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = 0.30

# cyclorama backdrop
import bmesh
me = bpy.data.meshes.new("cyc"); bm = bmesh.new()
prof = [(-6.0, 0.0)] + [(2.2 + 1.2 * sin(a), 1.2 - 1.2 * cos(a)) for a in [radians(x) for x in range(0, 91, 6)]] + [(3.4, 7.0)]
rows = []
for (y, z) in prof:
    rows.append([bm.verts.new((x, y, z)) for x in (-8, 8)])
for a, b in zip(rows[:-1], rows[1:]):
    bm.faces.new((a[0], a[1], b[1], b[0]))
bm.to_mesh(me); bm.free()
for p in me.polygons: p.use_smooth = True
cyc = bpy.data.objects.new("cyc", me); sc.collection.objects.link(cyc)
m = bpy.data.materials.new("cycmat"); m.use_nodes = True
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.36, 0.345, 0.33, 1); b.inputs["Roughness"].default_value = 0.55
me.materials.append(m)
cyc.rotation_euler = (0, 0, radians(az))

def area(name, loc, size, power, color=(1, 1, 1), target=(0, 0, 0.55)):
    L = bpy.data.lights.new(name, "AREA"); L.shape = "RECTANGLE"; L.size = size[0]; L.size_y = size[1]
    L.energy = power; L.color = color
    o = bpy.data.objects.new(name, L); sc.collection.objects.link(o); o.location = loc
    d = Vector(target) - Vector(loc); o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return o

def polar(a_deg, e_deg, r, z0=0.55):
    a, e = radians(a_deg), radians(e_deg)
    return (r * sin(a) * cos(e), -r * cos(a) * cos(e), z0 + r * sin(e))

area("key", polar(az - 48, 42, 3.0), (1.8, 1.8), 170, (1.0, 0.96, 0.90))
area("fill", polar(az + 55, 18, 3.2), (2.5, 2.5), 30, (0.92, 0.96, 1.0))
area("rim", polar(az + 165, 35, 2.8), (0.8, 2.2), 75, (1.0, 0.97, 0.93))
area("top", (0, 0, 3.0), (1.6, 1.6), 35)


# render-only antique glaze: darken crevices of the lacquered wood (the saved .blend / GLB stay untouched)
wm = bpy.data.materials.get("Wood_Lacquer")
if wm:
    nt2 = wm.node_tree; bs = nt2.nodes["Principled BSDF"]
    src = bs.inputs["Base Color"].links[0].from_socket
    ao = nt2.nodes.new("ShaderNodeAmbientOcclusion"); ao.inputs["Distance"].default_value = 0.025; ao.samples = 8
    ramp = nt2.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[0].color = (0.22, 0.17, 0.15, 1)
    ramp.color_ramp.elements[1].position = 0.85
    mix = nt2.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1.0
    nt2.links.new(ao.outputs["AO"], ramp.inputs["Fac"])
    nt2.links.new(src, mix.inputs[6]); nt2.links.new(ramp.outputs["Color"], mix.inputs[7])
    nt2.links.new(mix.outputs[2], bs.inputs["Base Color"])

cam_d = bpy.data.cameras.new("cam"); cam_d.lens = lens; cam_d.sensor_width = 36
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
cp = polar(az, el, dist, tz)
cam.location = (cp[0] + tgt[0], cp[1] + tgt[1], cp[2])
cam.rotation_euler = (Vector(tgt) - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
if view.startswith("detail"):
    cam_d.dof.use_dof = True; cam_d.dof.focus_distance = (Vector(tgt) - Vector(cam.location)).length; cam_d.dof.aperture_fstop = 8.0

bpy.ops.render.render(write_still=True)
print("RENDERED", outp)
