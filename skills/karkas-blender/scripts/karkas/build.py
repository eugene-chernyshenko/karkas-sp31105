"""Построение каркаса в Blender. Требует bpy (запускать внутри Blender)."""
from __future__ import annotations

import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

from .geom import Member
from .model import Result

# Цвета по типам элементов (base color, RGBA)
PALETTE = {
    "stud":          (0.82, 0.62, 0.36, 1.0),
    "cripple":       (0.86, 0.70, 0.46, 1.0),
    "plate":         (0.70, 0.46, 0.24, 1.0),
    "sill_plate":    (0.48, 0.34, 0.22, 1.0),
    "header":        (0.85, 0.35, 0.22, 1.0),
    "header_filler": (0.70, 0.45, 0.40, 1.0),
    "sill_board":    (0.88, 0.55, 0.30, 1.0),
    "joist":         (0.55, 0.65, 0.80, 1.0),
    "rim":           (0.38, 0.50, 0.70, 1.0),
    "girder":        (0.25, 0.35, 0.60, 1.0),
    "post":          (0.30, 0.30, 0.45, 1.0),
    "bridging":      (0.65, 0.75, 0.85, 1.0),
    "rafter":        (0.45, 0.70, 0.50, 1.0),
    "ceiling_joist": (0.60, 0.78, 0.62, 1.0),
    "ridge":         (0.25, 0.50, 0.32, 1.0),
    "gable_stud":    (0.72, 0.80, 0.55, 1.0),
    "fascia":        (0.35, 0.58, 0.42, 1.0),
    "roof_beam":     (0.45, 0.70, 0.50, 1.0),
    "subfloor":      (0.80, 0.78, 0.72, 0.30),
    "sheathing_ext": (0.86, 0.84, 0.76, 0.85),
    "sheathing_int": (0.93, 0.93, 0.90, 0.85),
    "insulation":    (0.95, 0.86, 0.45, 0.55),
    "vapour":        (0.55, 0.75, 0.90, 0.40),
    "cladding":      (0.62, 0.45, 0.33, 1.0),
    "batten":        (0.78, 0.66, 0.48, 1.0),
    "ceiling":       (0.95, 0.95, 0.93, 0.85),
    "roof_deck":     (0.70, 0.62, 0.50, 0.90),
    "trimmer":       (0.30, 0.42, 0.65, 1.0),
    "cantilever":    (0.42, 0.55, 0.75, 1.0),
    "tread":         (0.80, 0.52, 0.28, 1.0),
    "foundation":    (0.55, 0.55, 0.58, 1.0),
}
DEFAULT_COLOR = (0.75, 0.60, 0.40, 1.0)


def _material(kind: str):
    name = f"karkas_{kind}"
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    col = PALETTE.get(kind, DEFAULT_COLOR)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = col
        bsdf.inputs["Roughness"].default_value = 0.75
        if col[3] < 1.0:
            bsdf.inputs["Alpha"].default_value = col[3]
            mat.blend_method = "BLEND"
    mat.diffuse_color = col
    return mat


# Псевдонимы для spec["hidden"] — чем можно назвать слой, чтобы его выключить.
# Значение ищется как подстрока в имени коллекции (без учёта регистра).
HIDE_ALIASES = {
    "фундамент": "Фундамент",       "foundation": "Фундамент",
    "перекрытие": "Перекрытие",     "floor": "Перекрытие",
    "стены": "Стены",               "walls": "Стены",
    "внутренние": "Внутренние",     "interior": "Внутренние",
    "крыша": "Крыша",               "roof": "Крыша",
    "утеплитель": "Утеплитель",     "insulation": "Утеплитель",
    "утеплитель_стен": "Утеплитель_стен",
    "утеплитель_чердака": "Утеплитель_чердака",
}


def hide_collections(names, *, viewport=True, render=True) -> list[str]:
    """Выключает слои (коллекции) по именам или псевдонимам из HIDE_ALIASES.

    Гасит и галочку в View Layer (exclude), и иконку монитора (hide_viewport),
    и видимость в рендере. Состояние сохраняется в .blend.
    """
    if not names:
        return []
    requested = {}
    for n in names:
        key = str(n).strip()
        requested[HIDE_ALIASES.get(key.lower(), key).lower()] = key
    hidden, matched = [], set()
    for col in bpy.data.collections:
        hit = [n for n in requested if n in col.name.lower()]
        if not hit:
            continue
        matched.update(hit)
        if viewport:
            col.hide_viewport = True
        if render:
            col.hide_render = True
        hidden.append(col.name)
    for vl in bpy.context.scene.view_layers:
        for lc in vl.layer_collection.children:
            if lc.name in hidden:
                lc.exclude = True
    for n in sorted(set(requested) - matched):
        print(f"[!] слой '{requested[n]}' не найден — выключать нечего. "
              f"Известные псевдонимы: {', '.join(sorted(set(HIDE_ALIASES)))}",
              file=sys.stderr)
    return sorted(hidden)


def visible_objects(objs) -> list:
    """Объекты из невыключенных слоёв — то, что реально попадёт в рендер.

    Нужно для кадрирования камеры: иначе она охватывает и скрытую крышу.
    """
    off = {c.name for c in bpy.data.collections if c.hide_render or c.hide_viewport}
    if not off:
        return list(objs)
    kept = [o for o in objs if not any(c.name in off for c in o.users_collection)]
    return kept or list(objs)


def _collection(name: str, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def clear_scene(keep_worlds: bool = True):
    """Полная очистка сцены — вызывать перед генерацией."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                  bpy.data.cameras, bpy.data.lights):
        for b in list(block):
            if b.users == 0:
                block.remove(b)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def member_matrix(m: Member) -> Matrix:
    ax, wd, ht = m.basis
    rot = Matrix(((ax[0], wd[0], ht[0]), (ax[1], wd[1], ht[1]), (ax[2], wd[2], ht[2]))).to_4x4()
    return Matrix.Translation(Vector(m.center)) @ rot


def add_member(m: Member, collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(m.label)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(m.label, mesh)
    obj.matrix_world = member_matrix(m)
    obj.scale = Vector(m.size)
    obj.data.materials.append(_material(m.kind))
    obj["kind"] = m.kind
    obj["section"] = m.sec_str
    obj["length_m"] = round(m.length, 4)
    obj["sp_note"] = m.note
    collection.objects.link(obj)
    return obj


def add_panel(m: Member, collection) -> bpy.types.Object:
    """Плитный элемент (чёрный пол, настил) из meta['panel'] = (dx, dy, dz)."""
    dx, dy, dz = m.meta["panel"]
    mesh = bpy.data.meshes.new(m.label)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(m.label, mesh)
    obj.location = Vector(m.center)
    obj.scale = Vector((dx, dy, dz))
    obj.data.materials.append(_material(m.kind))
    obj["kind"] = m.kind
    obj["sp_note"] = m.note
    collection.objects.link(obj)
    return obj


def add_foundation(m: Member, collection) -> list:
    """Схематичная лента по периметру из meta['plan'] = (L, W, t, h)."""
    L, W, t, h = m.meta["plan"]
    objs = []
    segs = [((L / 2, -t / 2, -h / 2), (L + 2 * t, t, h)),
            ((L / 2, W + t / 2, -h / 2), (L + 2 * t, t, h)),
            ((-t / 2, W / 2, -h / 2), (t, W, h)),
            ((L + t / 2, W / 2, -h / 2), (t, W, h))]
    for i, (loc, size) in enumerate(segs):
        mesh = bpy.data.meshes.new(f"Фундамент {i + 1}")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(f"Фундамент {i + 1}", mesh)
        obj.location = Vector(loc)
        obj.scale = Vector(size)
        obj.data.materials.append(_material("foundation"))
        obj["kind"] = "foundation"
        obj["sp_note"] = m.note
        collection.objects.link(obj)
        objs.append(obj)
    return objs


def build(res: Result, *, apply_scale: bool = True, hidden=None) -> dict:
    """Создаёт объекты Blender из результата build_house()."""
    cols: dict[str, bpy.types.Collection] = {}
    created = []
    for m in res.members:
        col = cols.get(m.group) or _collection(m.group)
        cols[m.group] = col
        if m.meta.get("plan"):
            created += add_foundation(m, col)
        elif m.meta.get("panel"):
            created.append(add_panel(m, col))
        else:
            created.append(add_member(m, col))
    if apply_scale:
        bpy.ops.object.select_all(action="DESELECT")
        for o in created:
            o.select_set(True)
        if created:
            bpy.context.view_layer.objects.active = created[0]
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bpy.ops.object.select_all(action="DESELECT")
    off = hide_collections(hidden)
    return {"objects": created, "collections": cols, "hidden": off}


# --------------------------------------------------------------------------
# Камера, свет, рендер
# --------------------------------------------------------------------------
def bounds(objs) -> tuple[Vector, Vector]:
    import math
    lo = Vector((math.inf,) * 3)
    hi = Vector((-math.inf,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return lo, hi


def setup_scene(objs, *, view: str = "iso", resolution=(1920, 1080), engine: str = "BLENDER_EEVEE_NEXT"):
    """Солнце + HDRI-подобный фон + камера, охватывающая модель."""
    import math
    sc = bpy.context.scene
    try:
        sc.render.engine = engine
    except TypeError:
        sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = resolution
    sc.render.film_transparent = False

    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.70, 0.78, 0.88, 1.0)
        bg.inputs[1].default_value = 1.2

    sun_data = bpy.data.lights.new("Солнце", type="SUN")
    sun_data.energy = 3.5
    sun_data.angle = math.radians(2.0)
    sun = bpy.data.objects.new("Солнце", sun_data)
    sun.rotation_euler = (math.radians(50), 0, math.radians(135))
    sc.collection.objects.link(sun)

    lo, hi = bounds(objs)
    center = (lo + hi) / 2
    size = max((hi - lo).x, (hi - lo).y, (hi - lo).z)

    cam_data = bpy.data.cameras.new("Камера")
    cam_data.lens = 40
    cam = bpy.data.objects.new("Камера", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam

    dirs = {
        "iso":   Vector((1.0, -1.25, 1.6)),
        "front": Vector((0.0, -2.2, 0.35)),
        "side":  Vector((2.2, 0.0, 0.35)),
        "top":   Vector((0.01, -0.01, 2.6)),
    }
    d = dirs.get(view, dirs["iso"]).normalized()
    cam.location = center + d * size * 1.85
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return {"camera": cam, "sun": sun, "center": center, "size": size}


def render(path: str, samples: int = 32):
    sc = bpy.context.scene
    if hasattr(sc, "eevee"):
        try:
            sc.eevee.taa_render_samples = samples
        except AttributeError:
            pass
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    return path
