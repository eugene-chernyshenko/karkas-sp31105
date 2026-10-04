"""Параметрический генератор каркаса дома по СП 31-105-2002.

Чистый Python (без bpy): spec (dict) -> список Member + отчёт о соответствии.
Система координат: X — длина, Y — ширина, Z — вверх, метры.
Z = 0 — верх фундамента (низ нижней опорной доски).
(0, 0) — наружный угол каркаса наружных стен.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import rules as R
from .geom import Member, Vec, vadd, vmul

MM = 1 / 1000.0


# --------------------------------------------------------------------------
# Спецификация
# --------------------------------------------------------------------------
DEFAULT_SPEC = {
    "name": "karkas",
    "snow_kpa": 1.5,                  # расчётная снеговая нагрузка, кПа (СНиП 2.01.07)
    "storeys": 1,                     # надземных этажей (1..3)
    "plan": {"length": 9.0, "width": 7.0},   # по наружным граням каркаса, м
    "wall_height": 2.5,               # свободная высота стойки, м (табл. 7-1)
    "stud_spacing": 600,              # мм, 300/400/600
    "ext_stud": None,                 # None -> подбор по табл. 7-1
    "int_stud": "38x89",
    "sheathed": True,                 # жёсткая обшивка каркаса (влияет на табл. 7-1 и Б-13)
    "foundation": {"type": "strip", "plinth_height": 0.5},  # цоколь над землёй, м
    "floor": {
        "direction": "y",             # направление пролёта балок: 'x' | 'y'
        "spacing": 400,               # мм
        "joist": None,                # None -> подбор по табл. Б-1
        "bracing": "hv",              # h | v | hv (табл. Б-1)
        "subfloor_material": "plywood",
        "girder": "auto",             # 'auto' | None — промежуточный прогон, если пролёт велик
    },
    "roof": {
        "type": "gable",              # gable | flat
        "ridge_axis": "x",            # ось конька: 'x' | 'y'
        "slope": "1:2",               # подъём:заложение ("1:2") или число rise/run
        "rafter_spacing": 600,        # мм
        "overhang_eave": 0.5,         # карнизный свес по горизонтали, м
        "overhang_gable": 0.4,        # свес над фронтоном, м
        "attic": "cold",              # cold (неэксплуатируемый чердак) | living (мансарда)
        "rafter": None,               # None -> подбор по Б-6/Б-7
        "ceiling_joist": None,        # None -> подбор по Б-3 (cold) / Б-1 (living)
        "ridge_board": 38,            # толщина коньковой доски, мм (>=19 по 8.2.2.2)
    },
    "openings": [],                   # см. docstring frame_wall
    "interior_walls": [],             # [{"axis":"x"|"y","pos":м,"bearing":bool,"openings":[...]}]
}


def merge_spec(user: dict | None) -> dict:
    """Глубокое слияние пользовательской спецификации с умолчаниями."""
    out = {k: (dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v))
           for k, v in DEFAULT_SPEC.items()}
    for k, v in (user or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


@dataclass
class Result:
    members: list[Member] = field(default_factory=list)
    findings: list[tuple[str, str, str]] = field(default_factory=list)  # (уровень, узел, текст)
    levels: dict = field(default_factory=dict)
    picked: dict = field(default_factory=dict)

    def ok(self, node: str, msg: str): self.findings.append(("OK", node, msg))
    def warn(self, node: str, msg: str): self.findings.append(("WARN", node, msg))
    def err(self, node: str, msg: str): self.findings.append(("ERR", node, msg))

    @property
    def errors(self): return [f for f in self.findings if f[0] == "ERR"]


def parse_slope(s) -> float:
    """'1:2' -> 0.5 (подъём/заложение). Число возвращается как есть."""
    if isinstance(s, (int, float)):
        return float(s)
    a, b = s.split(":")
    return float(a) / float(b)


def slope_key(slope: float) -> str:
    """Ближайший снизу ключ таблицы 8-1."""
    keys = [("1:3", 1 / 3), ("1:2.4", 1 / 2.4), ("1:2", 1 / 2),
            ("1:1.71", 1 / 1.71), ("1:1.33", 1 / 1.33), ("1:1", 1.0)]
    best = keys[0][0]
    for k, v in keys:
        if slope >= v - 1e-9:
            best = k
    return best


def module_positions(length: float, spacing_mm: int, t_mm: int) -> list[float]:
    """Центры стоек: первая и последняя заподлицо с торцами, остальные по модулю."""
    t = t_mm * MM
    s = spacing_mm * MM
    pos = [t / 2]
    u = s
    while u < length - t:
        pos.append(u)
        u += s
    pos.append(length - t / 2)
    out = []
    for p in pos:
        if not out or p - out[-1] > t * 0.9:
            out.append(round(p, 6))
    return out


# --------------------------------------------------------------------------
# Каркас одной стены
# --------------------------------------------------------------------------
def frame_wall(res: Result, *, origin: tuple[float, float], d: Vec, n: Vec,
               length: float, z_base: float, stud: str, spacing_mm: int,
               height: float, group: str, openings: list[dict] | None = None,
               top_plates: int = 2, bearing: bool = True, bottom_plate: bool = True,
               corner_nailers: tuple[bool, bool] = (False, False),
               load_case: str = "attic", wall_kind: str = "external",
               snow_kpa: float = 1.5, sheathed: bool = True,
               name: str = "стена") -> dict:
    """Каркас одной прямой стены платформенного типа (7.2).

    origin — точка начала НАРУЖНОЙ грани стены (x, y) при z_base.
    d — единичный вектор вдоль стены, n — наружу (горизонтальный).
    z_base — отметка низа нижней обвязки.
    openings: [{"u": от начала стены до левого края проёма, "width":, "height":,
                "sill": низ проёма над z_base+38мм, "type": "window"|"door"}]
    corner_nailers: добавить стойку «плашмя» в начале/конце (угол на 3 стойках, 7.2.11).

    Возвращает dict с ключевыми отметками.
    """
    t_mm, h_mm = R.sec(stud)
    t, h = t_mm * MM, h_mm * MM
    openings = openings or []

    def P(u: float, inset: float, z: float) -> Vec:
        return (origin[0] + d[0] * u - n[0] * inset,
                origin[1] + d[1] * u - n[1] * inset, z)

    mid = h / 2
    z_bp_top = z_base + (0.038 if bottom_plate else 0.0)
    z_stud_top = z_bp_top + height
    z_wall_top = z_stud_top + 0.038 * top_plates

    add = res.members.append

    # --- нижняя обвязка (1 доска, 7.2.6) ---
    if bottom_plate:
        add(Member("plate", f"Нижняя обвязка ({name})", (38, h_mm),
                   P(0, mid, z_base + 0.019), P(length, mid, z_base + 0.019), (0, 0, 1),
                   group, "7.2.6/7.2.7: 1 доска, толщина ≥38, ширина ≥ высоты сечения стойки"))

    # --- верхняя обвязка (2 доски в несущих стенах, 7.2.6) ---
    for i in range(top_plates):
        z = z_stud_top + 0.019 + 0.038 * i
        add(Member("plate", f"Верхняя обвязка {i + 1} ({name})", (38, h_mm),
                   P(0, mid, z), P(length, mid, z), (0, 0, 1), group,
                   "7.2.6: верхняя обвязка из 2 досок; стыки верхней доски смещены на шаг стоек"))

    # --- разметка проёмов ---
    blocked: list[tuple[float, float]] = []
    for op in openings:
        u0, w = op["u"], op["width"]
        blocked.append((u0 - 2 * t, u0 + w + 2 * t))

    def free(u: float) -> bool:
        return all(not (a - t / 2 < u < b + t / 2) for a, b in blocked)

    # --- рядовые стойки ---
    for u in module_positions(length, spacing_mm, t_mm):
        if free(u):
            add(Member("stud", f"Стойка {stud} ({name})", (t_mm, h_mm),
                       P(u, mid, z_bp_top), P(u, mid, z_stud_top), d, group,
                       "7.2.4: стойка цельная по всей высоте этажа"))

    # --- угловые стойки «плашмя» для крепления внутренней обшивки (7.2.11) ---
    for side, want in zip((0, 1), corner_nailers):
        if not want:
            continue
        u = t * 1.5 if side == 0 else length - t * 1.5
        add(Member("stud", f"Угловая стойка-нашивка {stud} ({name})", (h_mm, t_mm),
                   P(u, t / 2, z_bp_top), P(u, t / 2, z_stud_top), d, group,
                   "7.2.11: третья стойка угла, длинной стороной параллельно стене"))

    # --- проёмы ---
    for op in openings:
        u0, w = op["u"], op["width"]
        head = op.get("height", 2.05) + op.get("sill", 0.0)
        sill_h = op.get("sill", 0.0)
        otype = op.get("type", "window")
        tag = f"{otype} {w:.2f}x{op.get('height', 2.05):.2f} м"

        if head > height - 1e-6:
            res.err(f"{name}/проём @{u0:.2f}",
                    f"верх проёма {head:.3f} м выше свободной высоты стойки {height:.3f} м")
            continue

        # перемычка (7.2.14, Б-12/Б-13)
        depth = op.get("header_depth")
        span_clear = w
        if depth is None:
            depth = R.pick_lintel(span_clear, load_case if load_case in R.T_B12 else "roof",
                                  snow_kpa=snow_kpa, wall=wall_kind, sheathed=sheathed)
            if depth is None:
                res.err(f"{name}/перемычка @{u0:.2f}",
                        f"пролёт {span_clear:.2f} м не перекрывается 2х(38x286) — нужен расчёт "
                        f"или составная перемычка по Б-14")
                depth = 286
            else:
                res.ok(f"{name}/перемычка @{u0:.2f}",
                       f"2х(38x{depth}) на пролёт {span_clear:.2f} м "
                       f"({'Б-13' if sheathed and wall_kind == 'external' else 'Б-12'})")
        z_head = z_bp_top + head
        # две доски на ребро + заполнение до толщины стены (7.2.14)
        for i in range(2):
            off = 0.019 + 0.038 * i   # две доски вплотную, от наружной грани внутрь
            add(Member("header", f"Перемычка 38x{depth} ({name}, {tag})", (38, depth),
                       P(u0 - t, off, z_head + depth * MM / 2),
                       P(u0 + w + t, off, z_head + depth * MM / 2), (0, 0, 1), group,
                       "7.2.14: 2 доски на ребро, толщина перемычки = ширине стоек у проёма"))
        filler = h_mm - 76
        if filler > 0:
            add(Member("header_filler", f"Прокладка перемычки {filler}x{depth} ({name})",
                       (filler, depth),
                       P(u0 - t, 0.076 + filler * MM / 2, z_head + depth * MM / 2),
                       P(u0 + w + t, 0.076 + filler * MM / 2, z_head + depth * MM / 2), (0, 0, 1),
                       group, "7.2.14: прокладка (дерево или жёсткий утеплитель) до толщины стены"))

        # стойки у проёма: опорные (jack) + крайние (king), 7.2.13
        for u, lab in ((u0 - t / 2, "опорная"), (u0 + w + t / 2, "опорная")):
            add(Member("stud", f"Стойка {lab} {stud} ({name})", (t_mm, h_mm),
                       P(u, mid, z_bp_top), P(u, mid, z_head), d, group,
                       "7.2.13: внутренняя стойка проёма — от нижней обвязки до перемычки"))
        for u in (u0 - 1.5 * t, u0 + w + 1.5 * t):
            add(Member("stud", f"Стойка крайняя {stud} ({name})", (t_mm, h_mm),
                       P(u, mid, z_bp_top), P(u, mid, z_stud_top), d, group,
                       "7.2.13: наружная стойка проёма — от нижней до верхней обвязки"))

        # укороченные стойки над перемычкой
        z_above = z_head + depth * MM
        if z_stud_top - z_above > 0.05:
            for u in module_positions(w, spacing_mm, t_mm):
                add(Member("cripple", f"Стойка укороченная {stud} ({name}, над перемычкой)",
                           (t_mm, h_mm), P(u0 + u, mid, z_above), P(u0 + u, mid, z_stud_top),
                           d, group, "конструктивно: заполнение над перемычкой по модулю стоек"))

        # подоконная доска и укороченные стойки под ней
        if otype != "door" and sill_h > 0.05:
            z_sill = z_bp_top + sill_h
            add(Member("sill_board", f"Подоконная доска 38x{h_mm} ({name}, {tag})", (38, h_mm),
                       P(u0, mid, z_sill - 0.019), P(u0 + w, mid, z_sill - 0.019), (0, 0, 1),
                       group, "конструктивный элемент (в СП 31-105 явно не нормируется)"))
            for u in module_positions(w, spacing_mm, t_mm):
                add(Member("cripple", f"Стойка укороченная {stud} ({name}, под окном)",
                           (t_mm, h_mm), P(u0 + u, mid, z_bp_top), P(u0 + u, mid, z_sill - 0.038),
                           d, group, "конструктивно: заполнение под проёмом по модулю стоек"))

    return {"z_base": z_base, "z_bottom_plate_top": z_bp_top,
            "z_stud_top": z_stud_top, "z_wall_top": z_wall_top, "depth": h}


# --------------------------------------------------------------------------
# Платформа перекрытия (раздел 6)
# --------------------------------------------------------------------------
def frame_platform(res: Result, spec: dict, *, z_base: float, group: str,
                   storeys_above: int, table: str = "B1", on_foundation: bool = False,
                   joist_override: str | None = None, spacing_override: int | None = None,
                   label: str = "перекрытие") -> dict:
    """Каркас перекрытия: опорная доска, обвязочные балки, балки, прогон, связи.

    Возвращает {'z_top': отметка верха чёрного пола, 'joist': сечение, 'depth': м}.
    """
    L = spec["plan"]["length"]
    W = spec["plan"]["width"]
    fl = spec["floor"]
    direction = fl["direction"]
    spacing = int(spacing_override or fl["spacing"])
    bracing = fl.get("bracing", "hv")
    add = res.members.append

    span_full = W if direction == "y" else L
    run_len = L if direction == "y" else W      # длина вдоль обвязочных балок

    # --- опорная доска по фундаменту (6.2.8.4) ---
    if on_foundation:
        sp_t, sp_h = R.sec(R.CLEARANCES["sill_plate"])
        for (p1, p2, wd) in (
            ((0, sp_h * MM / 2, z_base + sp_t * MM / 2), (L, sp_h * MM / 2, z_base + sp_t * MM / 2), (0, 0, 1)),
            ((0, W - sp_h * MM / 2, z_base + sp_t * MM / 2), (L, W - sp_h * MM / 2, z_base + sp_t * MM / 2), (0, 0, 1)),
            ((sp_h * MM / 2, 0, z_base + sp_t * MM / 2), (sp_h * MM / 2, W, z_base + sp_t * MM / 2), (0, 0, 1)),
            ((L - sp_h * MM / 2, 0, z_base + sp_t * MM / 2), (L - sp_h * MM / 2, W, z_base + sp_t * MM / 2), (0, 0, 1)),
        ):
            add(Member("sill_plate", "Нижняя опорная доска 38x88", (sp_t, sp_h), p1, p2, wd, group,
                       "6.2.8.4: по уровню на раствор/герметик, анкеры Ø≥12 мм с шагом ≤2,4 м, "
                       "заделка ≥100 мм"))
        res.ok(f"{label}/анкеровка",
               f"анкерных болтов Ø12: ≥{math.ceil(2 * (L + W) / 2.4) + 4} шт "
               f"(шаг ≤2400 мм по 6.2.8.4)")
        z0 = z_base + 0.038
    else:
        z0 = z_base

    # --- подбор балок, при необходимости — прогон (6.2.5, Б-1/Б-3, Б-8..Б-10) ---
    girder_mode = fl.get("girder", "auto")
    n_spans = 1
    sec_j = joist_override or fl.get("joist")
    if sec_j is None:
        sec_j = R.pick_joist(span_full, spacing, table=table, bracing=bracing)
        if sec_j is None and girder_mode == "auto":
            n_spans = 2
            sec_j = R.pick_joist(span_full / 2, spacing, table=table, bracing=bracing)
        if sec_j is None:
            res.err(f"{label}/балки",
                    f"пролёт {span_full:.2f} м не перекрывается ни одним сечением табл. {table} "
                    f"при шаге {spacing} мм — нужен расчёт или дополнительные опоры")
            sec_j = "38x286"
    else:
        lim = R.joist_max_span(sec_j, spacing, table=table, bracing=bracing)
        if span_full > lim + 1e-9:
            n_spans = 2 if girder_mode == "auto" else 1
            if n_spans == 2 and span_full / 2 > lim + 1e-9:
                res.err(f"{label}/балки",
                        f"{sec_j} при шаге {spacing} мм: предел {lim:.2f} м, "
                        f"пролёт {span_full / 2:.2f} м даже с прогоном посередине")
            elif n_spans == 1:
                res.err(f"{label}/балки",
                        f"{sec_j} при шаге {spacing} мм: предел {lim:.2f} м < пролёта {span_full:.2f} м")

    jt, jd = R.sec(sec_j)
    jdepth = jd * MM
    clear_span = span_full / n_spans
    lim = R.joist_max_span(sec_j, spacing, table=table, bracing=bracing)
    br = "" if table == "B3" else f", раскрепление '{bracing}'"
    if clear_span <= lim + 1e-9:
        res.ok(f"{label}/балки",
               f"{sec_j} @ {spacing} мм, пролёт {clear_span:.2f} м ≤ {lim:.2f} м "
               f"(табл. {table}{br})")
    else:
        res.err(f"{label}/балки",
                f"{sec_j} @ {spacing} мм: пролёт {clear_span:.2f} м > предела {lim:.2f} м "
                f"(табл. {table}{br})")

    if spacing > R.LIMITS["joist_spacing_mm"]:
        res.err(f"{label}/балки", f"шаг балок {spacing} мм > 600 мм — раздел 6 неприменим (6.2.4)")

    # --- обвязочные балки (6.2.8.5) по торцам балок ---
    zc = z0 + jdepth / 2
    if direction == "y":
        rims = [((0, jt * MM / 2, zc), (L, jt * MM / 2, zc)),
                ((0, W - jt * MM / 2, zc), (L, W - jt * MM / 2, zc))]
        ends = [((jt * MM / 2, 0, zc), (jt * MM / 2, W, zc)),
                ((L - jt * MM / 2, 0, zc), (L - jt * MM / 2, W, zc))]
    else:
        rims = [((jt * MM / 2, 0, zc), (jt * MM / 2, W, zc)),
                ((L - jt * MM / 2, 0, zc), (L - jt * MM / 2, W, zc))]
        ends = [((0, jt * MM / 2, zc), (L, jt * MM / 2, zc)),
                ((0, W - jt * MM / 2, zc), (L, W - jt * MM / 2, zc))]
    for p1, p2 in rims:
        add(Member("rim", f"Обвязочная балка {sec_j}", (jt, jd), p1, p2, (0, 0, 1), group,
                   "6.2.8.5: наружная грань заподлицо с наружной стороной каркаса стены"))
    _end_cuts = [(0.0, 1.0)] if n_spans == 1 else [(0.0, 0.5), (0.5, 1.0)]
    for p1, p2 in ends:
        for a, b in _end_cuts:
            q1 = tuple(p1[i] + (p2[i] - p1[i]) * a for i in range(3))
            q2 = tuple(p1[i] + (p2[i] - p1[i]) * b for i in range(3))
            add(Member("rim", f"Крайняя балка {sec_j}", (jt, jd), q1, q2, (0, 0, 1), group,
                       "6.2.1: крайние балки крепятся к обвязочным балкам"))

    # --- рядовые балки (при двухпролётной схеме разрезаются по прогону) ---
    axis_len = run_len
    gw_half = (0.0 if n_spans == 1 else 0.5 * 38 * MM * 3)   # уточняется ниже по сечению прогона
    cuts = [(0.0, span_full)] if n_spans == 1 else [(0.0, span_full / 2), (span_full / 2, span_full)]
    for u in module_positions(axis_len, spacing, jt):
        if u < jt * MM or u > axis_len - jt * MM:
            continue
        for (a, b) in cuts:
            if direction == "y":
                p1, p2 = (u, a, zc), (u, b, zc)
            else:
                p1, p2 = (a, u, zc), (b, u, zc)
            add(Member("joist", f"Балка перекрытия {sec_j}", (jt, jd), p1, p2, (0, 0, 1), group,
                       f"табл. {table}: шаг {spacing} мм"
                       + ("" if n_spans == 1 else "; опирание на боковую грань прогона "
                                                  "через уголки или опорные бруски (6.2.8.7)")))

    # --- промежуточный прогон составного сечения (6.2.6, Б-8..Б-10) ---
    if n_spans == 2:
        trib = span_full / 2
        gspan = axis_len
        pick = R.pick_girder(gspan, trib, min(3, max(1, storeys_above)))
        n_post = 1
        while pick is None and n_post < 6:
            n_post += 1
            pick = R.pick_girder(axis_len / n_post, trib, min(3, max(1, storeys_above)))
            gspan = axis_len / n_post
        if pick is None:
            res.err(f"{label}/прогон", "пролёт прогона не перекрывается табл. Б-8..Б-10 — нужен расчёт")
            pick = "5x286"
        nb, gd = pick.split("x")
        nb, gd = int(nb), int(gd)
        res.ok(f"{label}/прогон",
               f"{nb}х(38x{gd}), пролёт в свету {gspan:.2f} м, грузовая площадь {trib:.2f} м "
               f"(табл. Б-{7 + min(3, max(1, storeys_above))}); опирание ≥90 мм; "
               f"{n_post - 1 if n_post > 1 else 1} промежуточн. опор(ы)")
        gw = nb * 38 * MM
        gz = z0 + jdepth - gd * MM / 2
        if direction == "y":
            p1, p2 = (0, W / 2, gz), (L, W / 2, gz)
            wd = (0, 1, 0)
        else:
            p1, p2 = (L / 2, 0, gz), (L / 2, W, gz)
            wd = (1, 0, 0)
        add(Member("girder", f"Прогон составной {nb}х(38x{gd})", (nb * 38, gd), p1, p2, wd, group,
                   "6.2.6: доски ≥38 мм на ребро, сбиты гвоздями, стыки вразбежку над опорами"))
        post_base = float(spec.get("foundation", {}).get("post_base_z",
                          -abs(float(spec.get("foundation", {}).get("plinth_height", 0.5)))))
        z_girder_bottom = gz - gd * MM / 2
        for k in range(1, n_post):
            u = axis_len * k / n_post
            if direction == "y":
                px, py = u, W / 2
            else:
                px, py = L / 2, u
            if z_girder_bottom - post_base < 0.1:
                res.warn(f"{label}/опора прогона",
                         "высота опоры прогона <100 мм — проверьте отметки фундамента")
                continue
            add(Member("post", "Колонна под прогон 89x89", (89, 89),
                       (px, py, post_base), (px, py, z_girder_bottom), (1, 0, 0), group,
                       "5.5: колонна/столб под прогоном, закрепляется в центре фундамента; "
                       f"площадь подошвы по табл. 5-1 ≥{R.T5_1[min(3, max(1, storeys_above))]['column_m2']} м²"))

    # --- связи между балками (6.2.9) ---
    need_bridging = not spec.get("ceiling_rigid", True)
    rows = max(0, int(clear_span / 2.1))
    if rows and bracing != "none":
        for k in range(1, rows + 1):
            v = span_full * k / (rows + 1)
            if direction == "y":
                p1, p2 = (0, v, z0 + 0.019), (L, v, z0 + 0.019)
            else:
                p1, p2 = (v, 0, z0 + 0.019), (v, W, z0 + 0.019)
            add(Member("bridging", "Горизонтальная связь 19x64", (19, 64), p1, p2, (0, 0, 1), group,
                       "6.2.9.3: прибивается к низу балок, шаг ≤2100 мм от опор и друг от друга"))
    res.ok(f"{label}/связи",
           f"рядов связей: {rows} (6.2.9: шаг ≤2100 мм). Если подшивка потолка ГКЛ/ГВЛ/фанера "
           f"≥12 мм прямо по балкам — горизонтальное раскрепление не требуется (6.2.9.1)")

    # --- чёрный пол ---
    mat = fl.get("subfloor_material", "plywood")
    th = R.subfloor_min_thickness(spacing, mat)
    z_top = z0 + jdepth + th * MM
    res.ok(f"{label}/чёрный пол",
           f"{mat} ≥{th} мм при шаге балок {spacing} мм (табл. 6-2)")
    add(Member("subfloor", f"Чёрный пол {mat} {th:g} мм", (int(th), 1),
               (0, W / 2, z0 + jdepth + th * MM / 2), (L, W / 2, z0 + jdepth + th * MM / 2),
               (0, 0, 1), group, "табл. 6-2", meta={"panel": (L, W, th * MM)}))

    return {"z_top": z_top, "joist": sec_j, "depth": jdepth, "spacing": spacing,
            "subfloor_mm": th, "n_spans": n_spans}


# --------------------------------------------------------------------------
# Крыша (раздел 8)
# --------------------------------------------------------------------------
def frame_gable_roof(res: Result, spec: dict, *, z_plate_top: float, group: str,
                     wall_depth: float) -> dict:
    """Двускатная крыша, собираемая на месте (8.2.2 / 8.2.3)."""
    L, W = spec["plan"]["length"], spec["plan"]["width"]
    rf = spec["roof"]
    snow = float(spec["snow_kpa"])
    slope = parse_slope(rf["slope"])
    sp = int(rf["rafter_spacing"])
    ridge_axis = rf.get("ridge_axis", "x")
    oh_e = float(rf.get("overhang_eave", 0.5))
    oh_g = float(rf.get("overhang_gable", 0.4))
    add = res.members.append
    theta = math.atan(slope)
    cos_t = math.cos(theta)

    # ось конька вдоль X -> стропила пролётом по Y, и наоборот
    span_dir = W if ridge_axis == "x" else L
    run_dir = L if ridge_axis == "x" else W
    half = span_dir / 2.0

    if span_dir > R.LIMITS["house_width_for_roof_tables_m"] + 1e-9:
        res.err("крыша/область применения",
                f"ширина дома по пролёту стропил {span_dir:.2f} м > 9,8 м — таблицы Б-6/Б-7 "
                f"неприменимы (8.2.1.3), требуется расчёт")
    if sp > R.LIMITS["rafter_spacing_mm"]:
        res.err("крыша/шаг", f"шаг стропил {sp} мм > 600 мм (8.2.1.3)")
    if slope < 1 / 6:
        res.err("крыша/уклон", f"уклон {slope:.3f} < 1:6 — это плоская крыша (8.1.1), "
                               f"используйте roof.type='flat'")

    # --- стропила ---
    sec_r = rf.get("rafter") or R.pick_rafter(half, sp, snow)
    if sec_r is None:
        res.err("крыша/стропила",
                f"пролёт {half:.2f} м при шаге {sp} мм и снеге {snow} кПа не перекрывается "
                f"(Б-6/Б-7) — нужны промежуточные опоры (затяжки/стойки/раскосы, 8.2.1.1)")
        sec_r = "38x286"
    else:
        lim = R.rafter_max_span(sec_r, sp, snow)
        if half <= lim + 1e-9:
            res.ok("крыша/стропила",
                   f"{sec_r} @ {sp} мм, пролёт {half:.2f} м ≤ {lim:.2f} м "
                   f"(табл. Б-{'6' if snow <= 2.0 else '7'}, снег {snow} кПа)")
        else:
            res.err("крыша/стропила",
                    f"{sec_r} @ {sp} мм: пролёт {half:.2f} м > предела {lim:.2f} м")
    rt, rd = R.sec(sec_r)
    if spec["storeys"] >= 3 and rt < 89:
        res.warn("крыша/пожарные требования",
                 "8.2.1.5: в домах 3 этажа ширина сечения открытых стропил ≥89 мм")

    # --- балки чердачного перекрытия = затяжки (8.2.2.1) ---
    cold = rf.get("attic", "cold") == "cold"
    table_c = "B3" if cold else "B1"
    # промежуточная опора затяжек: внутренняя несущая стена параллельно коньку
    mid_support = rf.get("ceiling_mid_support", "auto")
    if mid_support == "auto":
        mid_support = any(
            iw.get("bearing") and iw.get("axis") == ridge_axis
            for iw in spec.get("interior_walls", []))
    c_span = span_dir / 2 if mid_support else span_dir
    sec_c = rf.get("ceiling_joist") or R.pick_joist(c_span, sp, table=table_c, bracing="hv")
    tie_mode = "затяжки по балкам чердачного перекрытия"
    if sec_c is None:
        c_span = span_dir / 2
        mid_support = True
        sec_c = R.pick_joist(c_span, sp, table=table_c, bracing="hv") or "38x286"
        res.warn("крыша/чердачное перекрытие",
                 f"полный пролёт {span_dir:.2f} м не перекрывается — принято {sec_c} с "
                 f"промежуточной опорой (внутренняя несущая стена посередине)")
    else:
        lim = R.joist_max_span(sec_c, sp, table=table_c, bracing="hv")
        res.ok("крыша/чердачное перекрытие",
               f"{sec_c} @ {sp} мм, пролёт {c_span:.2f} м ≤ {lim:.2f} м (табл. "
               f"{'Б-3, неэксплуатируемый чердак' if cold else 'Б-1, мансарда'})"
               + ("; промежуточная опора — внутренняя несущая стена посередине" if mid_support else ""))
    ct, cd = R.sec(sec_c)
    if mid_support:
        res.ok("крыша/затяжки",
               "8.2.2.5: при опирании затяжек на внутреннюю стену соединять их неразрезными "
               "связями ≥19x89 вблизи середины (затяжки длиной >2,4 м)")

    if slope >= 1 / 3 - 1e-9:
        res.ok("крыша/конёк", "8.2.2.1: уклон ≥1:3 — вертикальная опора под коньком не нужна, "
                              "распор воспринимают балки чердачного перекрытия (затяжки)")
        n_nails = R.rafter_tie_nails(slope_key(slope), sp, snow)
        if n_nails is None:
            res.err("крыша/узел стропило-балка",
                    f"табл. 8-1: сочетание уклон {slope_key(slope)} / шаг {sp} / снег {snow} кПа "
                    f"не допускается без расчёта")
        else:
            res.ok("крыша/узел стропило-балка",
                   f"табл. 8-1: ≥{n_nails} гвоздей 80 мм в соединении каждого стропила с балкой "
                   f"(в соединении балок между собой — на 1 гвоздь больше)")
    else:
        res.warn("крыша/конёк",
                 "8.2.3.1: уклон <1:3 — верхние концы стропил опирать на коньковую балку "
                 "≥38x140 по стойкам ≥38x89 с шагом 1,2 м на внутренней несущей стене")

    # --- геометрия ---
    z0 = z_plate_top                     # низ стропила на наружной грани стены
    plumb = rd * MM / cos_t              # вертикальный размер сечения стропила
    z_ridge_bottom = z0 + half * slope
    ridge_t = int(rf.get("ridge_board", 38))
    ridge_half = ridge_t * MM / 2

    def rafter_pair(u: float):
        """u — координата вдоль конька."""
        for sign in (-1, +1):
            # нижняя кромка: от свеса до конька
            a_s = -oh_e if sign < 0 else span_dir + oh_e
            a_e = half - ridge_half if sign < 0 else half + ridge_half
            if sign < 0:
                s_coord, e_coord = -oh_e, half - ridge_half
            else:
                s_coord, e_coord = span_dir + oh_e, half + ridge_half

            def pt(c):
                dist = abs(c - half)
                z = z_ridge_bottom - dist * slope + plumb / 2
                return (u, c, z) if ridge_axis == "x" else (c, u, z)
            wdir = (1, 0, 0) if ridge_axis == "x" else (0, 1, 0)
            add(Member("rafter", f"Стропило {sec_r}", (rt, rd), pt(s_coord), pt(e_coord), wdir,
                       group, "8.2.2.2/8.2.2.3: запил на опоре, площадка опирания ≥38 мм; "
                              "стропила противоположных скатов строго друг против друга"))

    def ceiling_joist(u: float):
        zc = z0 + cd * MM / 2
        segs = [(0.0, span_dir)] if not mid_support else [(0.0, half), (half, span_dir)]
        for a, b in segs:
            if ridge_axis == "x":
                p1, p2 = (u, a, zc), (u, b, zc)
            else:
                p1, p2 = (a, u, zc), (b, u, zc)
            add(Member("ceiling_joist", f"Балка чердачного перекрытия {sec_c}", (ct, cd), p1, p2,
                       (0, 0, 1), group,
                       f"8.2.2.1: работает как затяжка ({tie_mode})"
                       + ("; стык над внутренней несущей стеной внахлёст (8.2.2.4)"
                          if mid_support else "")))

    positions = module_positions(run_dir, sp, rt)
    for u in positions:
        rafter_pair(u)
        ceiling_joist(u)

    # --- коньковая доска (8.2.2.2) ---
    z_rb_top = z_ridge_bottom + plumb
    if ridge_axis == "x":
        p1, p2 = (-oh_g, half, z_rb_top - plumb / 2), (run_dir + oh_g, half, z_rb_top - plumb / 2)
        wd = (0, 1, 0)
    else:
        p1, p2 = (half, -oh_g, z_rb_top - plumb / 2), (half, run_dir + oh_g, z_rb_top - plumb / 2)
        wd = (1, 0, 0)
    add(Member("ridge", f"Коньковая доска {ridge_t}x{int(plumb * 1000)}",
               (ridge_t, int(plumb * 1000)), p1, p2, wd, group,
               "8.2.2.2: толщина ≥19 мм; стропила соединяются через неё встык"))

    # --- фронтонные стойки (8.4.1) ---
    stud_sec = spec["_ext_stud"]
    st, sh = R.sec(stud_sec)
    for end in (0.0, run_dir):
        inset = st * MM / 2 if end == 0 else -st * MM / 2
        for u in module_positions(span_dir, int(spec["stud_spacing"]), st):
            dist = abs(u - half)
            z_top = z_ridge_bottom - dist * slope
            if z_top - z0 < 0.25:
                continue   # короче 250 мм — заменяется распоркой
            if ridge_axis == "x":
                p1 = (end + inset, u, z0)
                p2 = (end + inset, u, z_top)
                wd = (0, 1, 0)
            else:
                p1 = (u, end + inset, z0)
                p2 = (u, end + inset, z_top)
                wd = (1, 0, 0)
            add(Member("gable_stud", f"Стойка фронтона {stud_sec}", (st, sh), p1, p2, wd, group,
                       "8.4.1: шаг и сечение как у нижележащей наружной стены, "
                       "стойки над стойками стены"))

    # --- обвязка стропил по карнизу (8.3.1) ---
    for sign in (0, 1):
        c = -oh_e if sign == 0 else span_dir + oh_e
        z = z_ridge_bottom - abs(c - half) * slope + plumb / 2
        if ridge_axis == "x":
            p1, p2 = (-oh_g, c, z), (run_dir + oh_g, c, z)
            wd = (0, 1, 0)
        else:
            p1, p2 = (c, -oh_g, z), (c, run_dir + oh_g, z)
            wd = (1, 0, 0)
        add(Member("fascia", f"Обвязка стропил (карниз) 38x{rd}", (38, rd), p1, p2, wd, group,
                   "8.3.1: толщина ≥38 мм, на неё опирается нижний край кровельного настила"))

    deck = R.roof_deck_min_thickness(sp, "plywood")
    res.ok("крыша/настил", f"фанера ≥{deck} мм при шаге стропил {sp} мм (табл. 8-6); "
                           f"волокна поверхности — поперёк стропил, зазоры между листами ≥2 мм")
    res.ok("крыша/вентиляция",
           f"8.7.6: площадь продухов ≥1/300 площади чердачного перекрытия "
           f"≈ {L * W / 300:.2f} м² (≥1/50 ≈ {L * W / 50:.2f} м² для III–IV климатических районов); "
           f"≥25 % вверху (фронтон) и ≥25 % внизу (карниз); зазор над утеплителем ≥60 мм (8.7.11)")
    if oh_g > 0.3:
        res.ok("крыша/фронтонный свес",
               "8.4.3/8.4.5: свес >300 мм — обвязочный брус ниже крайнего стропила, "
               "консольные балки сечением как стропила с шагом ≤600 мм, лобовая балка по торцам")
    if L * W >= 3.0 and (z_ridge_bottom - z0) >= 0.6:
        res.ok("крыша/доступ", "8.8: нужен люк-лаз ≥500x700 мм с крышкой и запирающим устройством")

    return {"rafter": sec_r, "ceiling_joist": sec_c, "z_ridge": z_rb_top,
            "slope": slope, "deck_mm": deck}


def frame_flat_roof(res: Result, spec: dict, *, z_plate_top: float, group: str) -> dict:
    """Плоская крыша на кровельных балках (8.2.5)."""
    L, W = spec["plan"]["length"], spec["plan"]["width"]
    rf = spec["roof"]
    snow = float(spec["snow_kpa"])
    sp = int(rf["rafter_spacing"])
    direction = rf.get("beam_direction", "y")
    span = W if direction == "y" else L
    run = L if direction == "y" else W
    oh = float(rf.get("overhang_eave", 0.4))
    add = res.members.append

    sec_b = rf.get("rafter") or R.pick_roof_beam(span, sp, snow)
    if sec_b is None:
        res.err("крыша/кровельные балки",
                f"пролёт {span:.2f} м при шаге {sp} мм и снеге {snow} кПа не перекрывается "
                f"(Б-4/Б-5) — нужны промежуточные опоры")
        sec_b = "38x286"
    else:
        lim = R.roof_beam_max_span(sec_b, sp, snow)
        res.ok("крыша/кровельные балки",
               f"{sec_b} @ {sp} мм, пролёт {span:.2f} м ≤ {lim:.2f} м "
               f"(табл. Б-{'4' if snow <= 2.0 else '5'})")
    bt, bd = R.sec(sec_b)
    res.ok("крыша/уклон", "8.2.5.3: уклон ≥1:50 подкладками под опорную часть балок")
    res.ok("крыша/вентиляция", f"8.7.6: площадь продухов ≥1/150 ≈ {L * W / 150:.2f} м²; "
                               f"зазор над утеплителем ≥60 мм (8.7.11)")

    z = z_plate_top + bd * MM / 2
    for u in module_positions(run, sp, bt):
        if direction == "y":
            p1, p2 = (u, -oh, z), (u, W + oh, z)
        else:
            p1, p2 = (-oh, u, z), (L + oh, u, z)
        add(Member("roof_beam", f"Кровельная балка {sec_b}", (bt, bd), p1, p2, (0, 0, 1), group,
                   "8.2.5: совмещает функции стропил и балок чердачного перекрытия; "
                   "крепление к обвязке — 2 гвоздя 80 мм вкосую"))
    return {"rafter": sec_b, "z_ridge": z_plate_top + bd * MM, "slope": 0.02}


# --------------------------------------------------------------------------
# Сборка дома
# --------------------------------------------------------------------------
def external_load_case(storeys: int, attic: str = "cold") -> str:
    """Строка табл. 7-1 для стоек наружных стен 1-го этажа."""
    extra = storeys - 1
    return "attic" if extra == 0 else f"attic+{min(3, extra)}"


def pick_ext_stud(res: Result, spec: dict, load_case: str) -> str:
    """Подбор сечения стойки наружной стены по табл. 7-1."""
    want = spec.get("ext_stud")
    sp = int(spec["stud_spacing"])
    h = float(spec["wall_height"])
    sheathed = bool(spec.get("sheathed", True))
    if want:
        ok, msg = R.check_stud(want, sp, h, "external", load_case, sheathed)
        (res.ok if ok else res.err)("стены/стойки", msg)
        return want
    for s, max_sp, max_h, _ in R.stud_options("external", load_case):
        if sp <= max_sp and (sheathed or h <= max_h):
            res.ok("стены/стойки",
                   f"подобрано {s} при шаге {sp} мм (табл. 7-1, «{load_case}», Hсвоб ≤{max_h} м). "
                   f"Для размещения утеплителя сечение можно увеличить (38x140/38x184) — "
                   f"это не слабее табличного")
            return s
    res.err("стены/стойки",
            f"табл. 7-1 («{load_case}») не допускает шаг {sp} мм ни при одном сечении; "
            f"варианты: " + ", ".join(f"{s}@≤{m}мм" for s, m, _, _ in
                                      R.stud_options("external", load_case)))
    return "38x140"


def build_house(user_spec: dict | None = None) -> Result:
    """Главная точка входа: спецификация -> каркас + отчёт о соответствии СП."""
    spec = merge_spec(user_spec)
    res = Result()
    L, W = spec["plan"]["length"], spec["plan"]["width"]
    storeys = int(spec["storeys"])
    H = float(spec["wall_height"])
    sp = int(spec["stud_spacing"])
    snow = float(spec["snow_kpa"])
    roof_type = spec["roof"].get("type", "gable")
    attic = spec["roof"].get("attic", "cold")

    # --- 4.2.1 границы применимости ---
    if storeys > R.LIMITS["storeys"]:
        res.err("общее/4.2.1", f"{storeys} этажа(ей) > 3 — СП неприменим")
    if sp not in R.SPACINGS:
        res.err("общее/шаг стоек", f"шаг {sp} мм отсутствует в таблицах СП (300/400/600)")
    if snow > 3.0:
        res.err("общее/снег", f"снеговая нагрузка {snow} кПа > 3,0 кПа — таблицы Б неприменимы")

    load_case = external_load_case(storeys, attic)
    ext_stud = pick_ext_stud(res, spec, load_case)
    spec["_ext_stud"] = ext_stud
    et, eh = R.sec(ext_stud)
    t_ext = eh * MM           # толщина наружной стены (глубина каркаса)

    # высота этажа от пола до пола — проверка 4.2.1
    storey_h = H + 0.038 * 3
    if storey_h > R.LIMITS["storey_height_m"] + 1e-6:
        res.warn("общее/4.2.1",
                 f"высота этажа ≈{storey_h:.2f} м > 3,0 м — выходит за условия 4.2.1")

    # --- фундамент ---
    f = R.foundation(storeys, masonry_veneer=spec.get("masonry_veneer", False))
    plinth = float(spec["foundation"].get("plinth_height", 0.5))
    res.ok("фундамент", f"табл. 5-1: лента под наружные стены ≥{f['ext_mm']} мм, "
                        f"под внутренние ≥{f['int_mm']} мм (этажей: {storeys}); "
                        f"верх цоколя ≥150 мм над землёй, низ деревянной обшивки ≥250 мм (5.4.7)")
    res.members.append(Member(
        "foundation", f"Лента фундамента {f['ext_mm']} мм", (f["ext_mm"], int(plinth * 1000)),
        (-f["ext_mm"] * MM / 2, W / 2, -plinth / 2), (L + f["ext_mm"] * MM / 2, W / 2, -plinth / 2),
        (0, 1, 0), "00_Фундамент",
        "условное отображение ленты по периметру; реальные размеры — табл. 5-1 и СНиП 2.02.01",
        meta={"schematic": True, "plan": (L, W, f["ext_mm"] * MM, plinth)}))

    # --- перекрытие над подпольем ---
    plat = frame_platform(res, spec, z_base=0.0, group="01_Перекрытие_1", storeys_above=storeys,
                          table="B1", on_foundation=True, label="перекрытие 1 этажа")
    z_floor = plat["z_top"]
    res.levels["floor_1"] = z_floor

    # --- наружные стены 1-го этажа ---
    walls = []
    # X-стены (полной длины), Y-стены (между ними)
    wall_defs = [
        ("S", (0.0, 0.0), (1, 0, 0), (0, -1, 0), L),
        ("N", (0.0, W), (1, 0, 0), (0, 1, 0), L),
        ("W", (0.0, t_ext), (0, 1, 0), (-1, 0, 0), W - 2 * t_ext),
        ("E", (L, t_ext), (0, 1, 0), (1, 0, 0), W - 2 * t_ext),
    ]
    ops_by_wall: dict[str, list] = {}
    for op in spec.get("openings", []):
        ops_by_wall.setdefault(op["wall"], []).append(
            {"u": op.get("u", op.get("x", 0.0)), "width": op["width"],
             "height": op["height"], "sill": op.get("sill", 0.0),
             "type": op.get("type", "window"), "header_depth": op.get("header_depth")})

    opening_area = {}
    for tag, origin, d, n, wlen in wall_defs:
        ops = ops_by_wall.get(tag, [])
        info = frame_wall(
            res, origin=origin, d=d, n=n, length=wlen, z_base=z_floor, stud=ext_stud,
            spacing_mm=sp, height=H, group="02_Стены_1", openings=ops, top_plates=2,
            bearing=True, corner_nailers=(tag in ("S", "N"), tag in ("S", "N")),
            load_case={"attic": "roof", "attic+1": "roof+1", "attic+2": "roof+2",
                       "attic+3": "roof+3"}[load_case],
            wall_kind="external", snow_kpa=snow, sheathed=bool(spec.get("sheathed", True)),
            name=f"наружная {tag}")
        walls.append(info)
        area = wlen * H
        oa = sum(o["width"] * o["height"] for o in ops)
        opening_area[tag] = (oa, area)
        if area > 0 and oa / area > R.LIMITS["opening_area_fraction"] + 1e-9:
            res.err(f"стены/{tag}",
                    f"площадь проёмов {oa:.2f} м² = {oa / area * 100:.0f} % площади стены "
                    f"{area:.2f} м² > 30 % (4.2.1)")
        elif oa:
            res.ok(f"стены/{tag}",
                   f"проёмов {oa:.2f} м² = {oa / area * 100:.0f} % площади стены (≤30 %, 4.2.1)")

    z_plate_top = walls[0]["z_wall_top"]
    res.levels["wall_top_1"] = z_plate_top

    # --- внутренние стены ---
    for i, iw in enumerate(spec.get("interior_walls", []), 1):
        istud = iw.get("stud", spec["int_stud"])
        it, ih = R.sec(istud)
        bearing = bool(iw.get("bearing", False))
        icase = ("roof" if bearing else "none") if storeys == 1 else (
            "roof+1" if bearing else "none")
        # для ненесущих перегородок табл. 7-1 («Отсутствует») допускает шаг ≤400 мм
        isp = int(iw.get("spacing", sp if bearing else min(sp, 400)))
        ok, msg = R.check_stud(istud, isp, H, "internal", icase,
                               bool(spec.get("sheathed", True)))
        (res.ok if ok else res.err)(f"внутренняя стена {i}", msg)
        if iw["axis"] == "x":
            origin = (iw.get("from", t_ext), iw["pos"])
            d, n = (1, 0, 0), (0, -1, 0)
            wlen = iw.get("to", L - t_ext) - origin[0]
        else:
            origin = (iw["pos"], iw.get("from", t_ext))
            d, n = (0, 1, 0), (-1, 0, 0)
            wlen = iw.get("to", W - t_ext) - origin[1]
        frame_wall(res, origin=origin, d=d, n=n, length=wlen, z_base=z_floor, stud=istud,
                   spacing_mm=isp, height=H, group="03_Внутренние_стены",
                   openings=[{"u": o.get("u", 0.0), "width": o["width"], "height": o["height"],
                              "sill": o.get("sill", 0.0), "type": o.get("type", "door"),
                              "header_depth": o.get("header_depth")}
                             for o in iw.get("openings", [])],
                   top_plates=2 if bearing else 1, bearing=bearing,
                   load_case="roof" if bearing else "attic", wall_kind="internal",
                   snow_kpa=snow, sheathed=bool(spec.get("sheathed", True)),
                   name=f"внутренняя {i}" + (" (несущая)" if bearing else " (перегородка)"))
        if not bearing:
            res.ok(f"внутренняя стена {i}/опирание",
                   "6.3.1: перегородка опирается на чёрный пол; при положении параллельно балкам "
                   "между ними — на распорки 38x89 с шагом 1,2 м (6.3.2)")
        else:
            res.ok(f"внутренняя стена {i}/опирание",
                   "6.3.4: несущая внутренняя стена опирается через чёрный пол на прогон или "
                   "нижележащую несущую стену; смещение от опоры балок ≤900 мм (чердак) / ≤600 мм")

    # --- вышележащие этажи ---
    z_cur = z_plate_top
    for s in range(2, storeys + 1):
        plat_n = frame_platform(res, spec, z_base=z_cur, group=f"0{s}a_Перекрытие_{s}",
                                storeys_above=storeys - s + 1, table="B1",
                                label=f"перекрытие {s} этажа")
        z_fl = plat_n["z_top"]
        tops = []
        for tag, origin, d, n, wlen in wall_defs:
            info = frame_wall(res, origin=origin, d=d, n=n, length=wlen, z_base=z_fl,
                              stud=ext_stud, spacing_mm=sp, height=H, group=f"0{s}b_Стены_{s}",
                              openings=[], top_plates=2, bearing=True,
                              corner_nailers=(tag in ("S", "N"), tag in ("S", "N")),
                              load_case="roof", wall_kind="external", snow_kpa=snow,
                              sheathed=bool(spec.get("sheathed", True)),
                              name=f"наружная {tag} эт.{s}")
            tops.append(info["z_wall_top"])
        z_cur = tops[0]
        res.levels[f"wall_top_{s}"] = z_cur

    # --- крыша ---
    if roof_type == "flat":
        roof = frame_flat_roof(res, spec, z_plate_top=z_cur, group="10_Крыша")
    else:
        roof = frame_gable_roof(res, spec, z_plate_top=z_cur, group="10_Крыша",
                                wall_depth=t_ext)
    res.levels["ridge"] = roof["z_ridge"]
    res.picked = {"ext_stud": ext_stud, "stud_spacing": sp, "floor_joist": plat["joist"],
                  "floor_spacing": plat["spacing"], "subfloor_mm": plat["subfloor_mm"],
                  **{k: v for k, v in roof.items() if k != "z_ridge"},
                  "load_case_table_7_1": load_case}

    # --- обшивки ---
    sh_gkl = R.sheathing_min_thickness(sp, "gkl")
    sh_ply = R.sheathing_min_thickness(sp, "plywood")
    res.ok("обшивки",
           f"табл. 7-3 при шаге стоек {sp} мм: ГКЛ/ГВЛ ≥{sh_gkl} мм, фанера ≥{sh_ply} мм, "
           f"пиломатериал ≥18 мм. Все края листов — над опорами (7.3.5.3)")
    if storeys >= 3:
        res.ok("пожарные требования",
               "табл. 7-4: 3 этажа — шаг стоек ≤600 мм, ГКЛ/ГВЛ ≥12,5 мм с каждой стороны "
               "(≥24 мм в два слоя при площади этажа >150 м²), утеплитель НГ или Г1; "
               "винты с шагом ≤300 мм")

    return res


# --------------------------------------------------------------------------
# Спецификация материалов
# --------------------------------------------------------------------------
def bom(members: list[Member]) -> list[dict]:
    """Ведомость пиломатериалов: группировка по названию/сечению/длине."""
    acc: dict[tuple, dict] = {}
    for m in members:
        if m.meta.get("schematic") or m.meta.get("panel"):
            continue
        key = (m.label.split(" (")[0], m.sec_str, round(m.length, 2))
        e = acc.setdefault(key, {"name": key[0], "section": key[1], "length_m": key[2],
                                 "count": 0, "total_m": 0.0, "volume_m3": 0.0})
        e["count"] += 1
        e["total_m"] += m.length
        e["volume_m3"] += m.volume
    rows = sorted(acc.values(), key=lambda r: (-r["volume_m3"], r["name"]))
    for r in rows:
        r["total_m"] = round(r["total_m"], 2)
        r["volume_m3"] = round(r["volume_m3"], 4)
    return rows


def report(res: Result) -> str:
    lines = []
    lines.append(f"ПРОВЕРКА ПО {R.SP}")
    lines.append("=" * 72)
    order = {"ERR": 0, "WARN": 1, "OK": 2}
    for lvl, node, msg in sorted(res.findings, key=lambda f: order[f[0]]):
        mark = {"ERR": "✗", "WARN": "!", "OK": "✓"}[lvl]
        lines.append(f"{mark} [{node}] {msg}")
    lines.append("")
    lines.append("ПРИНЯТЫЕ СЕЧЕНИЯ")
    lines.append("-" * 72)
    for k, v in res.picked.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("ОТМЕТКИ, м")
    lines.append("-" * 72)
    for k, v in res.levels.items():
        lines.append(f"  {k}: {v:.3f}")
    lines.append("")
    rows = bom(res.members)
    total_v = sum(r["volume_m3"] for r in rows)
    total_n = sum(r["count"] for r in rows)
    lines.append(f"ВЕДОМОСТЬ ПИЛОМАТЕРИАЛОВ — {total_n} шт, {total_v:.3f} м³")
    lines.append("-" * 72)
    lines.append(f"{'Наименование':<46}{'Сечение':>9}{'Длина':>7}{'Шт':>5}{'м³':>8}")
    for r in rows:
        lines.append(f"{r['name'][:45]:<46}{r['section']:>9}{r['length_m']:>7.2f}"
                     f"{r['count']:>5}{r['volume_m3']:>8.3f}")
    return "\n".join(lines)
