"""Image / scene / mesh I/O. Scene = zip(manifest.json, canvas.png, meshes/*.npz)."""

from __future__ import annotations

import base64
import json
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from Clay3D.canvas2d import Canvas
from Clay3D.scene3d import Mesh, Scene, SceneObject, Transform

SCENE_FORMAT = "clay3d-scene"
SCENE_VERSION = 3
MAX_IMAGE_PIXELS = 64_000_000
MAX_ZIP_MEMBER = 48 * 1024 * 1024
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}
# Both cases: some desktop file choosers match patterns case-sensitively.
IMAGE_FILTER = "Images ({})".format(
    " ".join(f"*{s} *{s.upper()}" for s in sorted(IMAGE_SUFFIXES))
)
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


# ---- images -------------------------------------------------------------


def save_image(canvas: Canvas, path: str | Path) -> None:
    path = Path(path)
    pixels = canvas.pixels
    if path.suffix.lower() in {".jpg", ".jpeg", ".bmp"}:
        alpha = pixels[:, :, 3:4].astype(np.float32) / 255.0
        flat = pixels[:, :, :3].astype(np.float32) * alpha + 255.0 * (1.0 - alpha)
        Image.fromarray(flat.astype(np.uint8), "RGB").save(path, quality=95)
        return
    Image.fromarray(pixels, "RGBA").save(path)


# Save as > Image: the original's file types, in its order.
EXPORT_TYPES = (
    ("PNG", ".png", True),     # name, suffix, keeps transparency
    ("JPEG", ".jpg", False),
    ("BMP", ".bmp", False),
    ("GIF", ".gif", True),
    ("TIFF", ".tif", True),
)


def export_pixels(pixels: np.ndarray, width: int, height: int, transparent: bool) -> np.ndarray:
    """The picture as it will be saved: scaled, and flattened on white unless transparent."""
    image = Image.fromarray(pixels, "RGBA")
    if image.size != (width, height):
        image = image.resize((max(1, width), max(1, height)), Image.Resampling.LANCZOS)
    out = np.array(image)
    if not transparent:
        alpha = out[:, :, 3:4].astype(np.float32) / 255.0
        out[:, :, :3] = (out[:, :, :3] * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
        out[:, :, 3] = 255
    return out


def encode_image(pixels: np.ndarray, type_name: str) -> bytes:
    """Encoded file bytes for one of EXPORT_TYPES; used for File size and for saving."""
    keeps_alpha = dict((name, alpha) for name, _, alpha in EXPORT_TYPES)[type_name]
    image = Image.fromarray(pixels, "RGBA")
    if not keeps_alpha:
        image = image.convert("RGB")
    buffer = BytesIO()
    options = {"quality": 95} if type_name == "JPEG" else {}
    image.save(buffer, format=type_name, **options)
    return buffer.getvalue()


def pixels_from_path(path: str | Path) -> np.ndarray | None:
    path = Path(path)
    if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
        return None
    return load_image(path).pixels


def load_image(path: str | Path) -> Canvas:
    with Image.open(path) as image:
        image.load()
        return _canvas_from_pil(image)


def _canvas_from_pil(image: Image.Image) -> Canvas:
    if image.size[0] * image.size[1] > MAX_IMAGE_PIXELS:
        raise ValueError("image too large")
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    pixels = np.array(image)   # a copy: arrays viewed from PIL are read-only, and tools paint on this
    canvas = Canvas(pixels.shape[1], pixels.shape[0], background=(0, 0, 0, 0))
    canvas.pixels = pixels
    return canvas


def _zip_read(archive: zipfile.ZipFile, name: str) -> bytes:
    name = name.replace("\\", "/")
    if name.startswith("/") or ".." in name.split("/"):
        raise ValueError("bad zip member")
    info = archive.getinfo(name)
    if info.file_size > MAX_ZIP_MEMBER:
        raise ValueError("zip member too large")
    return archive.read(name)


# ---- scenes -------------------------------------------------------------


def save_scene(scene: Scene, path: str | Path) -> None:
    manifest = {
        "format": SCENE_FORMAT,
        "version": SCENE_VERSION,
        "canvas": {
            "width": scene.canvas.width,
            "height": scene.canvas.height,
            "background": list(scene.canvas.background),
        },
        "camera": {
            "mode": scene.camera.mode,
            "yaw": scene.camera.yaw,
            "pitch": scene.camera.pitch,
            "distance": scene.camera.distance,
            "zoom": scene.camera.zoom,
            "target": scene.camera.target.tolist(),
        },
        "effect": scene.effect,
        "light_rotation": scene.light_rotation,
        "show_canvas": scene.show_canvas,
        "selected": scene.selected_index,
        "objects": [_object_manifest(obj, index) for index, obj in enumerate(scene.objects)],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=1))
        archive.writestr("canvas.png", _png_bytes(scene.canvas.pixels))
        for index, obj in enumerate(scene.objects):
            archive.writestr(f"meshes/{index}.npz", _mesh_bytes(obj.mesh))
            if obj.texture is not None:
                archive.writestr(f"textures/{index}.png", _png_bytes(obj.texture))


def load_scene(path: str | Path) -> Scene:
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError("bad zip member")
            if info.file_size > MAX_ZIP_MEMBER:
                raise ValueError("zip member too large")
        manifest = json.loads(_zip_read(archive, "manifest.json"))
        if manifest.get("format") != SCENE_FORMAT:
            raise ValueError("not a Clay3D scene")
        with Image.open(BytesIO(_zip_read(archive, "canvas.png"))) as image:
            image.load()
            canvas = _canvas_from_pil(image)
        canvas.background = tuple(manifest["canvas"].get("background", (255, 255, 255, 255)))

        scene = Scene(canvas=canvas)
        camera = manifest.get("camera", {})
        scene.camera.mode = camera.get("mode", "2d")
        scene.camera.yaw = camera.get("yaw", 0.0)
        scene.camera.pitch = camera.get("pitch", 0.28)
        scene.camera.distance = camera.get("distance", 8.0)
        scene.camera.zoom = camera.get("zoom", 1.0)
        scene.camera.target = np.array(camera.get("target", [0, 0, 0]), dtype=float)
        scene.effect = manifest.get("effect", "none")
        scene.light_rotation = manifest.get("light_rotation", 0.0)
        scene.show_canvas = manifest.get("show_canvas", True)

        objects = manifest.get("objects", [])
        if len(objects) > 4096:
            raise ValueError("too many objects")
        for index, entry in enumerate(objects):
            mesh = _mesh_from_bytes(_zip_read(archive, f"meshes/{index}.npz"))
            obj = SceneObject(
                kind=str(entry["kind"])[:64],
                mesh=mesh,
                transform=Transform(
                    position=np.array(entry["position"], dtype=float),
                    rotation=np.array(entry["rotation"], dtype=float),
                    scale=np.array(entry["scale"], dtype=float),
                ),
                color=tuple(entry["color"]),
                smoothness=float(entry.get("smoothness", 0.25)),
                metallic=float(entry.get("metallic", 0.0)),
            )
            if entry.get("has_texture"):
                with Image.open(BytesIO(_zip_read(archive, f"textures/{index}.png"))) as texture:
                    texture.load()
                    if texture.size[0] * texture.size[1] > MAX_IMAGE_PIXELS:
                        raise ValueError("texture too large")
                    obj.texture = np.ascontiguousarray(texture.convert("RGBA"))
            scene.objects.append(obj)
        scene.selected_index = int(manifest.get("selected", -1))
    return scene


def _object_manifest(obj: SceneObject, index: int) -> dict:
    return {
        "kind": obj.kind,
        "position": obj.transform.position.tolist(),
        "rotation": obj.transform.rotation.tolist(),
        "scale": obj.transform.scale.tolist(),
        "color": list(obj.color),
        "smoothness": obj.smoothness,
        "metallic": obj.metallic,
        "has_texture": obj.texture is not None,
    }


def _png_bytes(pixels: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(np.ascontiguousarray(pixels), "RGBA").save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def _mesh_bytes(mesh: Mesh) -> bytes:
    buffer = BytesIO()
    np.savez_compressed(
        buffer, positions=mesh.positions, normals=mesh.normals, uvs=mesh.uvs
    )
    return buffer.getvalue()


def _mesh_from_bytes(raw: bytes) -> Mesh:
    with np.load(BytesIO(raw), allow_pickle=False) as data:
        positions = np.asarray(data["positions"], dtype=float)
        normals = np.asarray(data["normals"], dtype=float)
        uvs = np.asarray(data["uvs"], dtype=float)
    if positions.ndim != 2 or positions.shape[0] > 2_000_000:
        raise ValueError("mesh too large")
    return Mesh(positions, normals, uvs)


# ---- 3D model export ----------------------------------------------------


MODEL_FORMATS = (
    ("obj", "Wavefront OBJ (*.obj)"),
    ("ply", "Stanford PLY (*.ply)"),
    ("stl", "Stereolithography (*.stl)"),
    ("gltf", "glTF 2.0 (*.gltf)"),
)


def save_model(scene: Scene, path: str | Path) -> None:
    path = Path(path)
    writer = {
        ".gltf": _save_gltf,
        ".ply": _save_ply,
        ".stl": _save_stl,
    }.get(path.suffix.lower(), _save_obj)
    writer(scene, path)


def _save_ply(scene: Scene, path: Path) -> None:
    """ASCII PLY + vertex colour."""
    vertices: list[str] = []
    faces: list[str] = []
    offset = 0
    for obj in scene.objects:
        world = _world_positions(obj)
        normals = (obj.transform.normal_matrix() @ obj.mesh.normals.T).T
        r, g, b, _ = obj.color
        for (x, y, z), (nx, ny, nz) in zip(world, normals):
            vertices.append(f"{x:.6f} {y:.6f} {z:.6f} {nx:.6f} {ny:.6f} {nz:.6f} {r} {g} {b}")
        for triangle in range(obj.mesh.triangle_count):
            a = offset + triangle * 3
            faces.append(f"3 {a} {a + 1} {a + 2}")
        offset += obj.mesh.vertex_count

    header = [
        "ply",
        "format ascii 1.0",
        "comment Clay3D export",
        f"element vertex {len(vertices)}",
        "property float x", "property float y", "property float z",
        "property float nx", "property float ny", "property float nz",
        "property uchar red", "property uchar green", "property uchar blue",
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    path.write_text("\n".join(header + vertices + faces) + "\n", encoding="utf-8")


def _save_stl(scene: Scene, path: Path) -> None:
    """ASCII STL. Geometry only."""
    lines = ["solid Clay3D"]
    for obj in scene.objects:
        world = _world_positions(obj)
        normals = (obj.transform.normal_matrix() @ obj.mesh.normals.T).T
        for triangle in range(obj.mesh.triangle_count):
            corners = world[triangle * 3 : triangle * 3 + 3]
            normal = normals[triangle * 3]
            lines.append(f"  facet normal {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}")
            lines.append("    outer loop")
            lines.extend(f"      vertex {x:.6f} {y:.6f} {z:.6f}" for x, y, z in corners)
            lines.append("    endloop")
            lines.append("  endfacet")
    lines.append("endsolid Clay3D")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _save_obj(scene: Scene, path: Path) -> None:
    lines = ["# Clay3D export"]
    offset = 1
    for index, obj in enumerate(scene.objects):
        world = _world_positions(obj)
        normals = obj.transform.normal_matrix() @ obj.mesh.normals.T
        normals = normals.T
        lines.append(f"o {obj.kind}_{index}")
        lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in world)
        lines.extend(f"vn {x:.6f} {y:.6f} {z:.6f}" for x, y, z in normals)
        lines.extend(f"vt {u:.6f} {v:.6f}" for u, v in obj.mesh.uvs)
        for triangle in range(obj.mesh.triangle_count):
            a, b, c = (offset + triangle * 3 + i for i in range(3))
            lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
        offset += obj.mesh.vertex_count
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _save_gltf(scene: Scene, path: Path) -> None:
    """glTF 2.0, buffer inlined as data URI."""
    buffer = bytearray()
    accessors: list[dict] = []
    buffer_views: list[dict] = []
    meshes: list[dict] = []
    nodes: list[dict] = []
    materials: list[dict] = []

    for index, obj in enumerate(scene.objects):
        positions = _world_positions(obj).astype(np.float32)
        normals = (obj.transform.normal_matrix() @ obj.mesh.normals.T).T.astype(np.float32)
        attributes = {}
        for name, data, kind in (
            ("POSITION", positions, "VEC3"),
            ("NORMAL", normals, "VEC3"),
            ("TEXCOORD_0", obj.mesh.uvs.astype(np.float32), "VEC2"),
        ):
            attributes[name] = len(accessors)
            accessors.append(
                {
                    "bufferView": len(buffer_views),
                    "componentType": 5126,
                    "count": len(data),
                    "type": kind,
                    "min": data.min(axis=0).tolist(),
                    "max": data.max(axis=0).tolist(),
                }
            )
            payload = np.ascontiguousarray(data).tobytes()
            buffer_views.append(
                {"buffer": 0, "byteOffset": len(buffer), "byteLength": len(payload), "target": 34962}
            )
            buffer.extend(payload)
            while len(buffer) % 4:
                buffer.append(0)

        r, g, b, a = obj.color
        materials.append(
            {
                "name": f"{obj.kind}_material",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [r / 255, g / 255, b / 255, a / 255],
                    "metallicFactor": float(obj.metallic),
                    "roughnessFactor": float(1.0 - obj.smoothness),
                },
                "doubleSided": True,
            }
        )
        meshes.append({"primitives": [{"attributes": attributes, "material": index}]})
        nodes.append({"mesh": index, "name": f"{obj.kind}_{index}"})

    document = {
        "asset": {"version": "2.0", "generator": "Clay3D"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [
            {
                "byteLength": len(buffer),
                "uri": "data:application/octet-stream;base64,"
                + base64.b64encode(bytes(buffer)).decode("ascii"),
            }
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def _world_positions(obj: SceneObject) -> np.ndarray:
    matrix = obj.transform.matrix()
    padded = np.hstack([obj.mesh.positions, np.ones((obj.mesh.vertex_count, 1))])
    return (matrix @ padded.T).T[:, :3]
