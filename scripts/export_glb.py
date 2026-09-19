"""Export the chair as a compressed web GLB. Run: blender -b out/chair.blend -P scripts/export_glb.py"""
import bpy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
dst = ROOT / "web" / "chair.glb"
dst.parent.mkdir(exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=str(dst), export_format="GLB", export_apply=True, export_yup=True,
    export_image_format="WEBP", export_image_quality=88,
    export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
    export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12,
    export_cameras=False, export_lights=False, export_animations=False)
print("GLB_BYTES", dst.stat().st_size)
