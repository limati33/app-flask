import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import struct
import gzip
import os
import math
from collections import deque, Counter

# Попытка импортировать внешние библиотеки
TRIMESH_AVAILABLE = True
PIL_AVAILABLE = True
try:
    import trimesh
    from trimesh import Trimesh
except Exception:
    TRIMESH_AVAILABLE = False
try:
    from PIL import Image
except Exception:
    PIL_AVAILABLE = False

# ==========================================
#          ПАЛИТРА БЛОКОВ 1.8
# ==========================================
COLOR_PALETTE = {
    (233, 233, 233): (35, 0),
    (219, 125, 62):  (35, 1),
    (179, 80, 188):  (35, 2),
    (107, 138, 201): (35, 3),
    (177, 166, 39):  (35, 4),
    (65, 174, 56):   (35, 5),
    (208, 132, 153): (35, 6),
    (64, 64, 64):    (35, 7),
    (154, 161, 161): (35, 8),
    (46, 110, 137):  (35, 9),
    (126, 61, 181):  (35, 10),
    (46, 56, 141):   (35, 11),
    (79, 50, 31):    (35, 12),
    (53, 70, 27):    (35, 13),
    (150, 52, 48):   (35, 14),
    (25, 22, 22):    (35, 15),

    (209, 177, 161): (159, 0),
    (161, 83, 37):   (159, 1),
    (149, 87, 108):  (159, 2),
    (113, 108, 137): (159, 3),
    (186, 133, 36):  (159, 4),
    (103, 117, 53):  (159, 5),
    (161, 78, 78):   (159, 6),
    (57, 42, 35):    (159, 7),
    (135, 107, 98):  (159, 8),
    (87, 92, 92):    (159, 9),
    (118, 70, 86):   (159, 10),
    (74, 59, 91):    (159, 11),
    (77, 51, 35):    (159, 12),
    (76, 83, 42):    (159, 13),
    (143, 61, 46):   (159, 14),
    (37, 22, 16):    (159, 15),

    (250, 250, 250): (80, 0),
    (235, 229, 222): (155, 0),
    (219, 211, 160): (12, 0),
    (125, 125, 125): (1, 0),
    (156, 156, 156): (98, 0),
    (115, 115, 115): (4, 0),
    (100, 100, 100): (1, 5),
    (150, 130, 110): (5, 0),
    (100, 80, 50):   (5, 1),
    (60, 45, 25):    (173, 0),

    (255, 215, 0):   (41, 0),
    (220, 220, 220): (42, 0),
    (45, 166, 152):  (57, 0),
    (30, 130, 10):   (133, 0),
    (74, 128, 255):  (22, 0),

    (100, 150, 150): (168, 0),
}

# Precompute LAB palette
def rgb_to_xyz(r, g, b):
    def f(c):
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else (c / 12.92)
    r, g, b = f(r), f(g), f(b)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    return x, y, z

def xyz_to_lab(x, y, z):
    xr, yr, zr = 0.95047, 1.00000, 1.08883
    x /= xr; y /= yr; z /= zr
    def f(t):
        return t ** (1/3) if t > 0.008856 else (7.787 * t + 16/116)
    fx, fy, fz = f(x), f(y), f(z)
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return (L, a, b)

def rgb_to_lab(rgb):
    r, g, b = rgb
    x, y, z = rgb_to_xyz(r/255.0, g/255.0, b/255.0)
    return xyz_to_lab(x, y, z)

PALETTE_LAB = {k: (v, rgb_to_lab(k)) for k, v in COLOR_PALETTE.items()}

def get_closest_block_lab(rgb):
    lab = rgb_to_lab(rgb)
    best = None
    min_d = float('inf')
    for pal_rgb, (block, pal_lab) in PALETTE_LAB.items():
        d = (lab[0]-pal_lab[0])**2 + (lab[1]-pal_lab[1])**2 + (lab[2]-pal_lab[2])**2
        if d < min_d:
            min_d = d
            best = block
    return best if best is not None else (35,0)

# ==========================================
#          OBJ / MTL PARSING (улучшённый)
# ==========================================
def parse_mtl(filename):
    materials = {}
    current_mtl = None
    if not os.path.exists(filename):
        return materials
    base_dir = os.path.dirname(filename)
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == 'newmtl':
                current_mtl = parts[1]
            elif parts[0] == 'Kd' and current_mtl:
                try:
                    r, g, b = map(float, parts[1:4])
                    materials[current_mtl] = (int(r*255), int(g*255), int(b*255))
                except:
                    pass
            elif parts[0] == 'map_Kd' and current_mtl:
                tex_path = os.path.join(base_dir, " ".join(parts[1:]))
                if os.path.exists(tex_path) and PIL_AVAILABLE:
                    try:
                        img = Image.open(tex_path).convert("RGB")
                        arr = np.array(img)
                        avg = arr.mean(axis=(0,1))
                        materials[current_mtl] = tuple(avg.astype(int))
                    except:
                        pass
    return materials

def load_obj_with_materials(filename):
    vertices = []
    faces = []  # tuples: (v0,v1,v2, mat_name)
    mtl_lib = {}
    base_dir = os.path.dirname(filename)

    uvs = []  # list of vt coordinates (from vt lines) (1-based in OBJ)
    vertex_uvs = []  # aligned with vertices (fill later, length == len(vertices))
    current_mat = "Default"

    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == 'mtllib':
                mtl_path = os.path.join(base_dir, " ".join(parts[1:]))
                mtl_lib = parse_mtl(mtl_path)
            elif parts[0] == 'usemtl':
                current_mat = parts[1]
            elif parts[0] == 'v':
                try:
                    vertices.append(list(map(float, parts[1:4])))
                    vertex_uvs.append(None)  # placeholder to align indexes
                except:
                    pass
            elif parts[0] == 'vt':
                try:
                    u = float(parts[1])
                    v = float(parts[2]) if len(parts) > 2 else 0.0
                    uvs.append((u, v))
                except:
                    uvs.append((0.0, 0.0))
            elif parts[0] == 'f':
                # face tokens can be v/vt/vn or v//vn or v
                face_vertices = []
                face_vts = []
                for tok in parts[1:]:
                    vals = tok.split('/')
                    vi = None
                    vti = None
                    try:
                        vi = int(vals[0]) - 1
                    except:
                        continue
                    if len(vals) >= 2 and vals[1] != '':
                        try:
                            vti = int(vals[1]) - 1
                        except:
                            vti = None
                    face_vertices.append((vi, vti))
                if len(face_vertices) < 3:
                    continue
                # triangulate fan
                for i in range(1, len(face_vertices) - 1):
                    a_vi, a_vti = face_vertices[0]
                    b_vi, b_vti = face_vertices[i]
                    c_vi, c_vti = face_vertices[i+1]
                    faces.append([a_vi, b_vi, c_vi, current_mat])
                    # map vt -> vertex_uvs if available
                    for (v_idx, vt_idx) in ((a_vi, a_vti), (b_vi, b_vti), (c_vi, c_vti)):
                        if vt_idx is not None and 0 <= vt_idx < len(uvs) and 0 <= v_idx < len(vertex_uvs):
                            # set vertex_uvs if not present
                            if vertex_uvs[v_idx] is None:
                                vertex_uvs[v_idx] = uvs[vt_idx]
    return np.array(vertices, dtype=float), faces, mtl_lib, vertex_uvs, {}

# ==========================================
#        Загрузка через trimesh (улучшённая)
# ==========================================
def average_image_color_from_pil_image(img):
    arr = np.array(img.convert("RGB"))
    avg = arr.mean(axis=(0,1))
    return tuple(int(x) for x in avg)

def pil_or_array_to_numpy(img):
    if img is None:
        return None
    if PIL_AVAILABLE and isinstance(img, Image.Image):
        return np.array(img.convert("RGB"))
    if isinstance(img, np.ndarray):
        # ensure shape H,W,3
        if img.ndim == 3 and img.shape[2] >= 3:
            return img[:, :, :3].astype(np.uint8)
    return None

def load_mesh_with_trimesh(path):
    """
    Загружает GLB/GLTF/FBX/прочие через trimesh.
    Возвращает: vertices (np.array), faces (list), materials (dict),
                vertex_uvs (list aligned with vertices, or []), material_textures (dict)
    """
    if not TRIMESH_AVAILABLE:
        raise RuntimeError("Требуется trimesh: pip install trimesh")

    try:
        scene = trimesh.load(path, process=False)
    except Exception as e:
        raise RuntimeError(f"Ошибка загрузки: {e}")

    if isinstance(scene, Trimesh):
        scene = trimesh.Scene(scene)

    all_vertices = []
    all_faces = []  # [i0,i1,i2, mat_name]
    materials = {}
    material_textures = {}
    vertex_uvs = []  # global UV list aligned with all_vertices
    vertex_offset = 0

    # scene.dump(concatenate=False) returns list of meshes with per-mesh transforms applied
    for mesh in scene.dump(concatenate=False):
        # attempt to extract per-mesh material/texture/uvs
        color_rgb = (200, 200, 200)
        found_color = False
        tex_img = None

        try:
            visual = getattr(mesh, 'visual', None)
            if visual is not None:
                # try texture image
                mat = getattr(visual, 'material', None)
                # trimesh sometimes exposes visual.material.image or visual.material.baseColorTexture
                if mat is not None:
                    # mat.image might be PIL image or ndarray
                    img = getattr(mat, 'image', None)
                    if img is None and hasattr(mat, 'pbrMetallicRoughness'):
                        pbr = mat.pbrMetallicRoughness
                        # sometimes pbr.baseColorTexture.image etc.
                        img = getattr(pbr, 'baseColorTexture', None)
                        # baseColorTexture may be small object; trimesh sometimes loads image into mat.image
                    if img is not None:
                        # if img is a PIL image or ndarray
                        tex_img = pil_or_array_to_numpy(img) if not isinstance(img, np.ndarray) else pil_or_array_to_numpy(img)
                        if tex_img is not None:
                            color_rgb = tuple(int(c) for c in tex_img.mean(axis=(0,1))[:3])
                            found_color = True
                    # try baseColorFactor fallback
                    base_col = getattr(mat, 'baseColorFactor', None)
                    if not found_color and base_col is not None:
                        if max(base_col[:3]) <= 1.0:
                            color_rgb = tuple(int(c*255) for c in base_col[:3])
                        else:
                            color_rgb = tuple(int(c) for c in base_col[:3])
                        found_color = True
                # else, visual.kind may hold colors or vertex colors
                if not found_color:
                    vc = getattr(visual, 'vertex_colors', None)
                    if vc is not None and len(vc) > 0:
                        avg_vc = np.array(vc).mean(axis=0)[:3]
                        color_rgb = tuple(int(x) for x in avg_vc)
                        found_color = True
        except Exception:
            pass

        # make material name
        mat_name = f"mat_{color_rgb[0]}_{color_rgb[1]}_{color_rgb[2]}"
        # store material color
        materials[mat_name] = color_rgb
        if tex_img is not None:
            # store texture as numpy array (H,W,3)
            material_textures[mat_name] = tex_img

        # add vertices and preserve UVs if present
        mesh_verts = np.array(mesh.vertices)
        n_verts = len(mesh_verts)
        # mesh.visual.uv shape usually matches mesh.vertices
        mesh_uvs = None
        try:
            if hasattr(mesh.visual, 'uv') and mesh.visual.uv is not None:
                mesh_uvs = np.array(mesh.visual.uv)
        except Exception:
            mesh_uvs = None

        for i in range(n_verts):
            all_vertices.append(mesh_verts[i])
            if mesh_uvs is not None and i < len(mesh_uvs):
                vertex_uvs.append(tuple(mesh_uvs[i]))
            else:
                vertex_uvs.append(None)

        # faces
        mesh_faces = np.array(mesh.faces)
        for f in mesh_faces:
            all_faces.append([int(f[0]) + vertex_offset, int(f[1]) + vertex_offset, int(f[2]) + vertex_offset, mat_name])

        vertex_offset += n_verts

    return np.array(all_vertices, dtype=float), all_faces, materials, vertex_uvs, material_textures

def load_model_auto(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        # OBJ loader returns 5 items now
        return load_obj_with_materials(path)
    else:
        return load_mesh_with_trimesh(path)

# ==========================================
#          GEOMETРИЧЕСКИЕ ХЕЛПЕРЫ
# ==========================================
def point_in_triangle_3d(p, a, b, c, normal):
    w = p - a
    dist = np.dot(w, normal)
    p_proj = p - dist * normal

    v0 = c - a
    v1 = b - a
    v2 = p_proj - a

    dot00 = np.dot(v0, v0)
    dot01 = np.dot(v0, v1)
    dot02 = np.dot(v0, v2)
    dot11 = np.dot(v1, v1)
    dot12 = np.dot(v1, v2)

    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < 1e-9:
        return False
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return (u >= -1e-6) and (v >= -1e-6) and (u + v <= 1.0 + 1e-6)

# ==========================================
#          ВОКСЕЛИЗАЦИЯ С UV SAMPLING
# ==========================================
def voxelize(vertices, faces, mtl_lib, target_height, fill_inside, progress_callback=None,
             vertex_uvs=None, material_textures=None):
    if progress_callback is None:
        def progress_callback(a,b,c=None): pass

    min_v = np.min(vertices, axis=0)
    max_v = np.max(vertices, axis=0)
    dims = max_v - min_v
    scale = float(target_height) / float(dims[1]) if dims[1] != 0 else 1.0
    scaled_v = (vertices - min_v) * scale
    max_coords = np.ceil(np.max(scaled_v, axis=0)).astype(int) + 2
    sx, sy, sz = tuple(max_coords.tolist())

    grid_id = np.zeros((sx, sy, sz), dtype=np.uint16)
    grid_data = np.zeros((sx, sy, sz), dtype=np.uint8)

    total_faces = len(faces)
    if total_faces == 0:
        return grid_id, grid_data

    # cache for face -> block to avoid repeated sampling for same material+uv
    face_block_cache = {}

    def choose_block_for_face(face):
        # face is [i0,i1,i2, mat_name]
        key = (face[0], face[1], face[2], face[3])
        if key in face_block_cache:
            return face_block_cache[key]

        mat_name = face[3]
        # try UV + texture sampling
        rgb = None
        try:
            if material_textures and mat_name in material_textures and vertex_uvs is not None:
                tex = material_textures[mat_name]
                tex_np = tex if isinstance(tex, np.ndarray) else (np.array(tex.convert("RGB")) if PIL_AVAILABLE and hasattr(tex, 'convert') else None)
                if tex_np is not None:
                    h, w = tex_np.shape[0], tex_np.shape[1]
                    # gather UVs from vertex_uvs (if present)
                    idx0, idx1, idx2 = face[0], face[1], face[2]
                    if idx0 < len(vertex_uvs) and idx1 < len(vertex_uvs) and idx2 < len(vertex_uvs):
                        uv0 = vertex_uvs[idx0]
                        uv1 = vertex_uvs[idx1]
                        uv2 = vertex_uvs[idx2]
                        if uv0 is not None and uv1 is not None and uv2 is not None:
                            u = float(uv0[0] + uv1[0] + uv2[0]) / 3.0
                            v = float(uv0[1] + uv1[1] + uv2[1]) / 3.0
                            u = max(0.0, min(1.0, u))
                            v = max(0.0, min(1.0, v))
                            px = int(u * (w - 1))
                            py = int((1.0 - v) * (h - 1))  # flip v
                            rgb = tuple(int(c) for c in tex_np[py, px][:3])
        except Exception:
            rgb = None

        # fallback to material average color from mtl_lib
        if rgb is None:
            if face[3] in mtl_lib:
                rgb = mtl_lib[face[3]]
            else:
                # fallback neutral
                rgb = (200,200,200)

        block = get_closest_block_lab(rgb)
        face_block_cache[key] = block
        return block

    # rasterize faces
    for idx, face in enumerate(faces):
        if idx % 50 == 0:
            progress_callback(idx, total_faces)
        try:
            v0 = scaled_v[face[0]]
            v1 = scaled_v[face[1]]
            v2 = scaled_v[face[2]]
        except Exception:
            continue

        b_id, b_data = choose_block_for_face(face)

        edge1 = v1 - v0
        edge2 = v2 - v0
        normal = np.cross(edge1, edge2)
        norm_len = np.linalg.norm(normal)
        if norm_len < 1e-9:
            continue
        normal = normal / norm_len

        tri_min = np.floor(np.min([v0, v1, v2], axis=0)).astype(int)
        tri_max = np.ceil(np.max([v0, v1, v2], axis=0)).astype(int)

        x0 = max(0, tri_min[0])
        y0 = max(0, tri_min[1])
        z0 = max(0, tri_min[2])
        x1 = min(sx - 1, tri_max[0])
        y1 = min(sy - 1, tri_max[1])
        z1 = min(sz - 1, tri_max[2])

        thresh = 0.866
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    p = np.array([x + 0.5, y + 0.5, z + 0.5])
                    dist = abs(np.dot(p - v0, normal))
                    if dist > thresh:
                        continue
                    if point_in_triangle_3d(p, v0, v1, v2, normal):
                        grid_id[x, y, z] = b_id
                        grid_data[x, y, z] = b_data

    progress_callback(total_faces, total_faces)

    # flood fill inside
    if fill_inside:
        progress_callback(0, 1, "Выполняется flood-fill внешней области...")
        visited = np.zeros_like(grid_id, dtype=bool)
        q = deque()
        sx, sy, sz = grid_id.shape
        def try_enqueue(xx, yy, zz):
            if 0 <= xx < sx and 0 <= yy < sy and 0 <= zz < sz:
                if not visited[xx, yy, zz] and grid_id[xx, yy, zz] == 0:
                    visited[xx, yy, zz] = True
                    q.append((xx, yy, zz))
        for x in range(sx):
            for y in range(sy):
                try_enqueue(x, y, 0); try_enqueue(x, y, sz-1)
        for x in range(sx):
            for z in range(sz):
                try_enqueue(x, 0, z); try_enqueue(x, sy-1, z)
        for y in range(sy):
            for z in range(sz):
                try_enqueue(0, y, z); try_enqueue(sx-1, y, z)
        while q:
            cx, cy, cz = q.popleft()
            for dx, dy, dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
                nx, ny, nz = cx+dx, cy+dy, cz+dz
                if 0 <= nx < sx and 0 <= ny < sy and 0 <= nz < sz:
                    if not visited[nx, ny, nz] and grid_id[nx, ny, nz] == 0:
                        visited[nx, ny, nz] = True
                        q.append((nx, ny, nz))
        inside_mask = (grid_id == 0) & (~visited)
        progress_callback(0, 1, "Заполнение внутренних полостей...")
        for _pass in range(200):
            changed = 0
            inside_coords = np.transpose(np.nonzero(inside_mask))
            if inside_coords.size == 0:
                break
            for coord in inside_coords:
                x, y, z = coord
                neighbor_blocks = []
                for dx, dy, dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
                    nx, ny, nz = x+dx, y+dy, z+dz
                    if 0 <= nx < sx and 0 <= ny < sy and 0 <= nz < sz:
                        nb = grid_id[nx, ny, nz]
                        if nb != 0:
                            neighbor_blocks.append((nb, grid_data[nx, ny, nz]))
                if neighbor_blocks:
                    ids = [b for b,d in neighbor_blocks]
                    most_common_id = Counter(ids).most_common(1)[0][0]
                    dat = next((d for (b,d) in neighbor_blocks if b == most_common_id), 0)
                    grid_id[x, y, z] = most_common_id
                    grid_data[x, y, z] = dat
                    inside_mask[x, y, z] = False
                    changed += 1
            if changed == 0:
                break

    progress_callback(1, 1, "Готово вокселизация.")
    return grid_id, grid_data

# ==========================================
#          NBT / SCHEMATIC WRITER
# ==========================================
def save_schematic(grid_id, grid_data, filename):
    sx, sy, sz = grid_id.shape
    width, height, length = sx, sy, sz

    blocks = bytearray(width * height * length)
    data = bytearray(width * height * length)

    idx = 0
    for y in range(height):
        for z in range(length):
            for x in range(width):
                bid = int(grid_id[x, y, z])
                bdata = int(grid_data[x, y, z])
                blocks[idx] = bid & 0xFF
                data[idx] = bdata & 0xFF
                idx += 1

    def write_tag(name, val, type_id):
        b = bytearray()
        if type_id == 2: # Short
            b.append(2)
            if name:
                b.extend(struct.pack('>H', len(name)))
                b.extend(name.encode('utf-8'))
            b.extend(struct.pack('>h', val))
        elif type_id == 7: # Byte Array
            b.append(7)
            if name:
                b.extend(struct.pack('>H', len(name)))
                b.extend(name.encode('utf-8'))
            b.extend(struct.pack('>i', len(val)))
            b.extend(val)
        elif type_id == 8: # String
            b.append(8)
            if name:
                b.extend(struct.pack('>H', len(name)))
                b.extend(name.encode('utf-8'))
            b.extend(struct.pack('>H', len(val)))
            b.extend(val.encode('utf-8'))
        return b

    nbt = bytearray()
    nbt.append(10) # Compound
    nbt.extend(struct.pack('>H', len("Schematic")))
    nbt.extend("Schematic".encode('utf-8'))

    nbt.extend(write_tag("Width", width, 2))
    nbt.extend(write_tag("Height", height, 2))
    nbt.extend(write_tag("Length", length, 2))
    nbt.extend(write_tag("Materials", "Alpha", 8))
    nbt.extend(write_tag("Blocks", blocks, 7))
    nbt.extend(write_tag("Data", data, 7))
    nbt.extend(b'\x09\x00\x08Entities\x0a\x00\x00\x00\x00')
    nbt.extend(b'\x09\x00\x0cTileEntities\x0a\x00\x00\x00\x00')
    nbt.append(0) # End

    with gzip.open(filename, 'wb') as f:
        f.write(nbt)

# ==========================================
#                  GUI
# ==========================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("3D -> Minecraft 1.8 Schematic (UV sampling)")
        self.root.geometry("520x560")

        style = ttk.Style()
        style.configure("TButton", padding=6)

        self.frame_file = ttk.LabelFrame(root, text="Выбор файла")
        self.frame_file.pack(pady=10, padx=10, fill="x")

        self.btn_file = ttk.Button(self.frame_file, text="Выбрать модель (.obj/.gltf/.glb/.fbx)", command=self.select_file)
        self.btn_file.pack(pady=5)
        self.lbl_file = ttk.Label(self.frame_file, text="Файл не выбран", foreground="gray")
        self.lbl_file.pack(pady=5)

        self.frame_settings = ttk.LabelFrame(root, text="Настройки")
        self.frame_settings.pack(pady=10, padx=10, fill="x")

        ttk.Label(self.frame_settings, text="Высота (блоков):").grid(row=0, column=0, padx=5, pady=5)
        self.ent_height = ttk.Entry(self.frame_settings, width=10)
        self.ent_height.insert(0, "64")
        self.ent_height.grid(row=0, column=1, padx=5, pady=5)

        self.var_fill = tk.BooleanVar(value=True)
        self.chk_fill = ttk.Checkbutton(self.frame_settings, text="Залить внутри (сплошной)", variable=self.var_fill)
        self.chk_fill.grid(row=1, column=0, columnspan=2, pady=5)

        self.var_color = tk.BooleanVar(value=True)
        self.chk_color = ttk.Checkbutton(self.frame_settings, text="Использовать цвета (шерсть/глина)", variable=self.var_color)
        self.chk_color.grid(row=2, column=0, columnspan=2, pady=5)

        # Optional: checkbox to enable UV-sampling (only when textures present)
        self.var_uv = tk.BooleanVar(value=True)
        self.chk_uv = ttk.Checkbutton(self.frame_settings, text="Использовать UV sampling (медленно)", variable=self.var_uv)
        self.chk_uv.grid(row=3, column=0, columnspan=2, pady=5)

        self.btn_run = ttk.Button(root, text="СОЗДАТЬ СХЕМУ", command=self.run_process, state="disabled")
        self.btn_run.pack(pady=20, fill="x", padx=20)

        self.progress = ttk.Progressbar(root, orient="horizontal", length=460, mode="determinate")
        self.progress.pack(pady=5)
        self.lbl_status = ttk.Label(root, text="Ожидание...")
        self.lbl_status.pack()

        self.input_path = ""

    def select_file(self):
        file = filedialog.askopenfilename(
            filetypes=[("3D Models", "*.obj *.gltf *.glb *.fbx"), ("OBJ", "*.obj"), ("glTF/GLB", "*.gltf *.glb"), ("FBX", "*.fbx")]
        )
        if file:
            self.input_path = file
            self.lbl_file.config(text=os.path.basename(file), foreground="black")
            self.btn_run.config(state="normal")

    def update_progress(self, current, total, text=None):
        try:
            percent = (current / total) * 100 if total != 0 else 0
        except:
            percent = 0
        self.progress['value'] = percent
        if text:
            self.lbl_status.config(text=text)
        else:
            self.lbl_status.config(text=f"Обработка: {int(percent)}%")
        self.root.update()

    def run_process(self):
        try:
            if not PIL_AVAILABLE:
                messagebox.showwarning("Зависимость отсутствует", "Pillow (PIL) не установлена. Установка рекомендована: pip install Pillow")
            if not TRIMESH_AVAILABLE:
                ext = os.path.splitext(self.input_path)[1].lower()
                if ext not in ['.obj']:
                    messagebox.showerror("Зависимость отсутствует", "Для загрузки этого формата требуется библиотека 'trimesh'. Установите: pip install trimesh")
                    return

            height = int(self.ent_height.get())
            fill = self.var_fill.get()
            use_color = self.var_color.get()
            use_uv = self.var_uv.get()

            output_path = filedialog.asksaveasfilename(defaultextension=".schematic",
                                                       filetypes=[("Minecraft Schematic", "*.schematic")])
            if not output_path:
                return

            self.lbl_status.config(text="Загрузка модели...")
            self.root.update()

            # load_model_auto returns either (verts, faces, mtl_lib, vertex_uvs, material_textures)
            data = load_model_auto(self.input_path)
            if len(data) == 3:
                verts, faces, mtl_lib = data
                vertex_uvs = None
                material_textures = {}
            else:
                verts, faces, mtl_lib, vertex_uvs, material_textures = data

            if not use_color:
                mtl_lib = {}
                material_textures = {}

            if not use_uv:
                vertex_uvs = None
                material_textures = {}

            self.lbl_status.config(text="Вокселизация...")
            self.root.update()
            grid_id, grid_data = voxelize(verts, faces, mtl_lib, height, fill, self.update_progress,
                                          vertex_uvs=vertex_uvs, material_textures=material_textures)

            self.lbl_status.config(text="Сохранение файла...")
            self.root.update()
            save_schematic(grid_id, grid_data, output_path)

            self.lbl_status.config(text="Готово!")
            messagebox.showinfo("Успех", f"Файл сохранен:\n{output_path}")

        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
