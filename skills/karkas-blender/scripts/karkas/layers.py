"""Слои ограждающих конструкций: обшивки, утеплитель, пароизоляция, облицовка.

Геометрия слоёв включается выключателями `spec["layers"]` — по умолчанию строится
только каркас и чёрный пол, чтобы листы не закрывали стойки.

Толщины берутся из таблиц СП (7-3, 6-2, 8-6) и пунктов 9.3, 10.3, 10.4.
Толщина УТЕПЛИТЕЛЯ таблицами СП не нормируется (9.2.1.2 отсылает к теплотехническому
расчёту по ГСОП, СНиП II-3 / СП 23-101) — она задаётся в спецификации, а модель
выдаёт предупреждение.
"""
from __future__ import annotations

from . import rules as R
from .geom import Member

MM = 1 / 1000.0

LAYER_DEFAULTS = {
    "wall_sheathing_ext": False,   # наружная защитная обшивка каркаса (7.3.2, 10.4.4.2)
    "wall_sheathing_int": False,   # внутренняя обшивка ГКЛ/ГВЛ (7.3.1, табл. 7-3)
    "wall_insulation": False,      # утеплитель между стойками (9.2.2.2 «а»)
    "vapour_barrier": False,       # пароизоляция с тёплой стороны (9.3.1)
    "cladding": False,             # облицовка по обрешётке с вентзазором (10.4.4)
    "ceiling": False,              # подшивка потолка (6.5, табл. 7-3)
    "attic_insulation": False,     # утеплитель чердачного перекрытия
    "roof_deck": False,            # кровельный настил (8.5, табл. 8-6)
}

# Толщина утеплителя по умолчанию, мм — НЕ норматив, требует теплотехнического расчёта
DEFAULT_ATTIC_INSULATION_MM = 250


def resolve(spec: dict) -> dict:
    """spec['layers'] -> полный словарь выключателей. Допускается 'all' / 'none'."""
    v = spec.get("layers", {})
    if v == "all":
        return {k: True for k in LAYER_DEFAULTS}
    if v in (None, "none", False):
        return dict(LAYER_DEFAULTS)
    out = dict(LAYER_DEFAULTS)
    out.update({k: bool(x) for k, x in v.items() if k in LAYER_DEFAULTS})
    return out


def _bay_segments(wall: dict) -> list[tuple[float, float, float, float]]:
    """Ячейки между стойками: (u1, u2, z1, z2) с вычетом проёмов."""
    t = R.sec(wall["stud"])[0] * MM
    axes = wall["stud_axes"]
    z0, z1 = wall["z_bottom_plate_top"], wall["z_stud_top"]
    out = []
    for a, b in zip(axes, axes[1:]):
        u1, u2 = a + t / 2, b - t / 2
        if u2 - u1 < 0.02:
            continue
        uc = (u1 + u2) / 2
        op = next((o for o in wall["openings"] if o["u"] - t <= uc <= o["u"] + o["width"] + t), None)
        if op is None:
            out.append((u1, u2, z0, z1))
            continue
        sill = z0 + op["sill"]
        head = z0 + op["head"]
        if op["type"] != "door" and sill - z0 > 0.05:
            out.append((u1, u2, z0, sill - 0.038))
        if z1 - head > 0.05:
            out.append((u1, u2, head, z1))
    return out


def wall_layers(res, wall: dict, on: dict, spec: dict, group: str) -> None:
    """Слои одной стены. wall — то, что вернул frame_wall()."""
    o, d, n = wall["origin"], wall["d"], wall["n"]
    L = wall["length"]
    depth = wall["depth"]
    sp = wall["spacing_mm"]
    z0, z1 = wall["z_bottom_plate_top"], wall["z_stud_top"]
    z_bot, z_top = wall["z_base"], wall["z_wall_top"]
    H = z_top - z_bot
    ext = wall["wall_kind"] == "external"
    add = res.members.append

    def slab(kind, label, thick_mm, offset, zc, h, note, length=None):
        """Плита по всей стене: offset — от наружной грани внутрь (+) / наружу (−)."""
        half = thick_mm * MM / 2
        c = offset + half
        p1 = (o[0] + d[0] * 0 - n[0] * c, o[1] + d[1] * 0 - n[1] * c, zc)
        p2 = (o[0] + d[0] * (length or L) - n[0] * c,
              o[1] + d[1] * (length or L) - n[1] * c, zc)
        add(Member(kind, label, (int(round(thick_mm)), int(round(h * 1000))),
                   p1, p2, n, group, note))

    # --- наружная защитная обшивка каркаса ---
    if on["wall_sheathing_ext"] and ext:
        th = max(R.sheathing_min_thickness(sp, "plywood"), 9.5)
        slab("sheathing_ext", f"Наружная обшивка фанера {th:g} мм", th, -th * MM, (z_bot + z_top) / 2, H,
             f"табл. 7-3 (жёсткость каркаса) и 10.4.4.2 (основание под облицовку); "
             f"≥9,5 мм также требуется для применения табл. Б-13 к перемычкам")

    # --- утеплитель между стойками ---
    if on["wall_insulation"] and ext:
        for u1, u2, a, b in _bay_segments(wall):
            zc, h = (a + b) / 2, b - a
            c = depth / 2
            p1 = (o[0] + d[0] * u1 - n[0] * c, o[1] + d[1] * u1 - n[1] * c, zc)
            p2 = (o[0] + d[0] * u2 - n[0] * c, o[1] + d[1] * u2 - n[1] * c, zc)
            add(Member("insulation", f"Утеплитель {int(depth * 1000)} мм", 
                       (int(depth * 1000), int(round(h * 1000))), p1, p2, n, group,
                       "9.2.2.2 «а»: в пространстве между стойками, обвязками и обшивками; "
                       "λ ≤0,10 Вт/(м·°C) (9.2.2.1). Толщина = глубине каркаса, "
                       "достаточность проверяется теплотехническим расчётом (9.2.1.2)"))

    # --- пароизоляция с тёплой стороны ---
    if on["vapour_barrier"] and ext:
        slab("vapour", "Пароизоляция (плёнка ≥0,15 мм)", 2, depth, (z_bot + z_top) / 2, H,
             "9.3.2.2: полиэтиленовая плёнка ≥0,15 мм с тёплой стороны утеплителя; "
             "в модели показана условной толщиной 2 мм")

    # --- внутренняя обшивка ---
    if on["wall_sheathing_int"]:
        th = R.sheathing_min_thickness(sp, "gkl")
        off = depth + (2 * MM if on["vapour_barrier"] and ext else 0.0)
        slab("sheathing_int", f"Внутренняя обшивка ГКЛ {th:g} мм", th, off, (z_bot + z_top) / 2, H,
             f"табл. 7-3: ГКЛ/ГВЛ ≥{th:g} мм при шаге стоек {sp} мм; "
             f"винты с шагом ≤300 мм (табл. 7-4), края листов над опорами (7.3.5.3)")
        if not ext:
            slab("sheathing_int", f"Внутренняя обшивка ГКЛ {th:g} мм", th, -th * MM,
                 (z_bot + z_top) / 2, H, "7.3.1: перегородки обшиваются с обеих сторон")

    # --- облицовка по обрешётке с вентзазором ---
    if on["cladding"] and ext:
        gap = R.CLEARANCES["masonry_veneer_gap_recommended"] * MM   # 38 мм
        base = R.sheathing_min_thickness(sp, "plywood") * MM if on["wall_sheathing_ext"] else 0.0
        bt, bh = (19, 38)
        for u in wall["stud_axes"]:
            c = -(base + gap / 2)
            p1 = (o[0] + d[0] * u - n[0] * c, o[1] + d[1] * u - n[1] * c, z0)
            p2 = (o[0] + d[0] * u - n[0] * c, o[1] + d[1] * u - n[1] * c, z1)
            add(Member("batten", f"Обрешётка {bt}x{bh}", (bh, bt), p1, p2, d, group,
                       "10.4.4.3: обрешётка ≥19x38 мм по каркасу; при креплении прямо к стойкам "
                       "≥19x65 мм при шаге 400 и ≥19x89 мм при шаге 600 (10.4.4.4)"))
        slab("cladding", "Облицовка 20 мм", 20, -(base + gap + 0.020),
             (z_bot + z_top) / 2, H,
             "10.3.2.2: зазор между облицовкой и обшивкой ≥25 мм, рекомендуется 38 мм; "
             "низ деревянной облицовки ≥250 мм над планировкой (5.4.7)")


def platform_layers(res, spec: dict, on: dict, plat: dict, group: str,
                    is_attic: bool = False) -> None:
    """Подшивка потолка и утеплитель чердачного перекрытия."""
    L, W = spec["plan"]["length"], spec["plan"]["width"]
    add = res.members.append
    sp = plat["spacing"]
    z_joist_bottom = plat["z_top"] - plat["subfloor_mm"] * MM - plat["depth"]

    if on["ceiling"]:
        th = R.sheathing_min_thickness(sp, "gkl")
        add(Member("ceiling", f"Подшивка потолка ГКЛ {th:g} мм", (int(th), 1),
                   (0, W / 2, z_joist_bottom - th * MM / 2),
                   (L, W / 2, z_joist_bottom - th * MM / 2), (0, 0, 1), group,
                   f"6.5.1 и табл. 7-3 (шаг балок {sp} мм вместо шага стоек): ГКЛ/ГВЛ ≥{th:g} мм. "
                   f"При ≥12 мм прямо по балкам горизонтальное раскрепление балок не требуется "
                   f"(6.2.9.1)", meta={"panel": (L, W, th * MM)}))

    if on["attic_insulation"] and is_attic:
        t_mm = int(spec.get("layers", {}).get("attic_insulation_mm",
                                              DEFAULT_ATTIC_INSULATION_MM)
                   if isinstance(spec.get("layers"), dict) else DEFAULT_ATTIC_INSULATION_MM)
        add(Member("insulation", f"Утеплитель чердачного перекрытия {t_mm} мм", (t_mm, 1),
                   (0, W / 2, z_joist_bottom + t_mm * MM / 2),
                   (L, W / 2, z_joist_bottom + t_mm * MM / 2), (0, 0, 1), group,
                   "9.2: толщина определяется теплотехническим расчётом по ГСОП "
                   "(9.2.1.2, СНиП II-3 / СП 23-101); над утеплителем оставить "
                   "вентилируемое пространство ≥60 мм (8.7.11)",
                   meta={"panel": (L, W, t_mm * MM)}))
        res.warn("утеплитель/чердачное перекрытие",
                 f"принято {t_mm} мм — это НЕ значение из СП. Толщина утеплителя таблицами "
                 f"не нормируется: 9.2.1.2 требует расчёта по ГСОП района строительства "
                 f"(СНиП II-3 / СП 23-101). Задайте layers.attic_insulation_mm по расчёту")


def roof_layers(res, spec: dict, on: dict, info: dict, group: str) -> None:
    """Подшивка потолка, утеплитель чердачного перекрытия и кровельный настил.

    info: z_ceiling_bottom, ceiling_spacing, rafter_spacing, slopes
          (список плоскостей скатов: (p1, p2, w_dir, length, width) уже посчитанных).
    """
    L, W = spec["plan"]["length"], spec["plan"]["width"]
    add = res.members.append

    if on["ceiling"]:
        th = R.sheathing_min_thickness(info["ceiling_spacing"], "gkl")
        z = info["z_ceiling_bottom"] - th * MM / 2
        add(Member("ceiling", f"Подшивка потолка ГКЛ {th:g} мм", (int(th), 1),
                   (0, W / 2, z), (L, W / 2, z), (0, 0, 1), group,
                   f"6.5.1 и табл. 7-3 (шаг балок {info['ceiling_spacing']} мм): ГКЛ/ГВЛ "
                   f"≥{th:g} мм. В домах 3 этажа — ≥12,5 мм по пожарным требованиям (8.1.2)",
                   meta={"panel": (L, W, th * MM)}))

    if on["attic_insulation"]:
        lay = spec.get("layers")
        t_mm = int(lay.get("attic_insulation_mm", DEFAULT_ATTIC_INSULATION_MM)
                   if isinstance(lay, dict) else DEFAULT_ATTIC_INSULATION_MM)
        z = info["z_ceiling_bottom"] + t_mm * MM / 2
        add(Member("insulation", f"Утеплитель чердачного перекрытия {t_mm} мм", (t_mm, 1),
                   (0, W / 2, z), (L, W / 2, z), (0, 0, 1), group,
                   "9.2: над утеплителем оставить вентилируемое пространство ≥60 мм (8.7.11); "
                   "укладывать так, чтобы не перекрывать продухи",
                   meta={"panel": (L, W, t_mm * MM)}))
        res.warn("утеплитель/чердачное перекрытие",
                 f"принято {t_mm} мм — это НЕ значение из СП. Толщина утеплителя таблицами "
                 f"не нормируется: 9.2.1.2 требует теплотехнического расчёта по ГСОП района "
                 f"(СНиП II-3 / СП 23-101). Задайте layers.attic_insulation_mm по расчёту")

    if on["roof_deck"]:
        th = R.roof_deck_min_thickness(info["rafter_spacing"], "plywood")
        for i, pl in enumerate(info.get("slopes", []), 1):
            p1, p2, wd, width = pl
            add(Member("roof_deck", f"Кровельный настил фанера {th:g} мм",
                       (int(round(width * 1000)), int(th)), p1, p2, wd, group,
                       f"табл. 8-6: фанера ≥{th:g} мм при шаге стропил "
                       f"{info['rafter_spacing']} мм; волокна поверхности поперёк стропил, "
                       f"зазоры между листами ≥2 мм (8.5.3, 8.5.4.2)"))
