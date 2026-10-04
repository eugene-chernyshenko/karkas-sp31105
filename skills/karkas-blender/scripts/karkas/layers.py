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
    "windproof": False,            # водовоздухозащитный слой, он же ветрозащита (9.3.2.8)
    "wall_sheathing_int": False,   # внутренняя обшивка ГКЛ/ГВЛ (7.3.1, табл. 7-3)
    "wall_insulation": False,      # утеплитель между стойками (9.2.2.2 «а»)
    "interior_insulation": False,  # заполнение внутренних стен — звукоизоляция (7.5.2)
    "insulation_stagger": True,    # швы смежных ячеек вразбежку (практика, не норма)
    "vapour_barrier": False,       # пароизоляция с тёплой стороны (9.3.1)
    "cladding": False,             # облицовка по обрешётке с вентзазором (10.4.4)
    "ceiling": False,              # подшивка потолка (6.5, табл. 7-3)
    "attic_insulation": False,     # утеплитель чердачного перекрытия
    "roof_deck": False,            # кровельный настил (8.5, табл. 8-6)
}

# Толщина утеплителя по умолчанию, мм — НЕ норматив, требует теплотехнического расчёта
DEFAULT_ATTIC_INSULATION_MM = 250

# Высота одной плиты утеплителя, мм. Ходовой размер минплиты — 1000x600 при шаге
# стоек 600; СП размеры плит не нормирует. 0 — не резать, заполнять ячейку целиком.
DEFAULT_PLATE_MM = 1000

# Толщина одной плиты утеплителя, мм. Глубина каркаса набирается слоями по
# столько, швы слоёв перекрываются. 0 — один кусок на всю глубину.
DEFAULT_LAYER_MM = 50

# Ходовой лист ОСП/ГКЛ, мм. Ширина взята кратной шагу стоек 600: по 7.3.5.3 все края
# листов должны лежать над опорами, а 1250 при шаге 600 на стойку не попадает.
# Лист обшивки, мм (короткая сторона, длинная). 2400 = 4 шага стойки по 600,
# 1200 = 2 шага: по 7.3.5.3 края листов обязаны лежать над опорами, и так это
# выполняется при любой ориентации. Ходовые 2500x1250 под шаг 600 не ложатся.
SHEET_MM = (1200, 2400)
# Как кладут лист: "h" — длинной стороной горизонтально (так кладут обычно),
# "v" — вертикально.
SHEET_LAY = "h"
# ГКЛ ходит листом 1200x2500 (а также 2700 и 3000) и вешается стоймя. Вразбежку
# его класть СП не требует: 6.4.6 про вразбежку — только о чёрном поле, а для
# обшивок стен 7.3.5.3 требует лишь, чтобы края лежали над опорами.
SHEET_INT_MM = (1200, 2500)
SHEET_INT_LAY = "v"
SHEET_INT_STAGGER = False
# Кусок обшивки короче этого не выделяют в отдельный лист, м.
MIN_PIECE = 0.30


def _up(mm: float) -> int:
    """Толщину по таблицам СП округляем только ВВЕРХ.

    int(round(12.5)) в Python даёт 12 — округление к чётному. Для табл. 7-3
    это означало ГКЛ 12 мм вместо нормативных 12,5: толщина ниже минимума.
    """
    import math
    return int(math.ceil(mm - 1e-9))

# Рулон плёнки: ширина и нахлёст, мм. 9.3.3.2 требует нахлёста ≥100 мм; полотнища
# кладут горизонтально, верхнее поверх нижнего.
ROLL_MM = (1500, 100)
# Ширина ленты по шву, мм. СП ширину не задаёт: 10.2.2 требует лишь проклейки
# швов липкой лентой. 50 мм — практика.
TAPE_MM = 50

MATERIAL_NAMES = {"osb": "ОСП", "plywood": "фанера", "lumber": "пиломатериал",
                  "dvp": "ДВП", "csp": "ЦСП", "gkl": "ГКЛ", "gvl": "ГВЛ"}

# 9.3.2.8: «материалы на древесной основе (например, из фанеры, древесностружечных
# плит, пиломатериалов)» — при такой наружной обшивке водовоздухозащитный слой
# обязателен. ЦСП с минеральным связующим сюда не отношу.
WOOD_BASED = {"osb", "plywood", "lumber", "dvp"}
DEFAULT_SHEATHING_EXT = "osb"

# Утеплитель — в своём слое, а не в слое стены/крыши: иначе выключатель крыши
# прячет и утеплитель чердачного перекрытия, а посмотреть на один утеплитель
# отдельно от каркаса нельзя.
G_SHEATHING_EXT = "13_Обшивка_наружная"
G_WINDPROOF = "14_Ветрозащита"
G_TAPE = "18_Проклейка_швов"
G_VAPOUR = "15_Пароизоляция"
G_SHEATHING_INT = "16_Обшивка_внутренняя"
G_CLADDING = "17_Облицовка"

G_INSULATION = "11_Утеплитель_стен"
G_INSULATION_ATTIC = "12_Утеплитель_чердака"


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


def _cavities(wall: dict) -> list[tuple[float, float, float, float]]:
    """Пустоты каркаса стены: прямоугольники (u1, u2, z1, z2), не занятые элементами.

    Считается точно по проекции всех построенных элементов стены в её плоскость,
    поэтому утеплитель гарантированно не пересекается со стойками, обвязками,
    перемычками и укороченными стойками. Проёмы вычитаются отдельно — дерева
    в них нет, но и пустотой каркаса они не являются.
    """
    z0, z1 = wall["z_bottom_plate_top"], wall["z_stud_top"]
    blocked = list(wall.get("solids", []))
    # Проём — не пустота каркаса: окно и дверь утеплять нечем. Без этого сюда
    # попадала плита от подоконной доски до перемычки и закрывала проём.
    for op in wall.get("openings", []):
        blocked.append((op["u"], op["u"] + op["width"],
                        z0 + op["sill"], z0 + op["head"]))
    solids = [s for s in blocked if s[3] > z0 + 1e-6 and s[2] < z1 - 1e-6]
    edges = sorted({round(v, 6) for s in solids for v in (s[0], s[1])}
                   | {0.0, round(wall["length"], 6)})
    out = []
    for a, b in zip(edges, edges[1:]):
        if b - a < 0.01:
            continue
        mid = (a + b) / 2
        spans = sorted((max(s[2], z0), min(s[3], z1))
                       for s in solids if s[0] < mid < s[1])
        cur = z0
        for p1, p2 in spans:
            if p1 > cur + 0.01:
                out.append((a, b, cur, p1))
            cur = max(cur, p2)
        if z1 - cur > 0.01:
            out.append((a, b, cur, z1))
    return out


def _cols(u_start: float, u_end: float, sw: float, axes, first: float = 1.0) -> list[float]:
    """Границы листов вдоль стены: шаг не больше листа, граница — на стойке.

    7.3.5.3 требует, чтобы края листов лежали над опорами, поэтому лист не
    обрезается по сетке, а доводится до ближайшей стойки в пределах своей длины.
    first — доля листа для первого шага (пол-листа в рядах вразбежку).
    """
    ax = sorted(a for a in axes if u_start + 1e-6 < a < u_end - 1e-6)
    out, cur, k = [u_start], u_start, first
    while cur < u_end - 1e-6:
        reach = cur + sw * k
        k = 1.0
        hit = [a for a in ax if cur + 1e-6 < a <= reach + 1e-9]
        nxt = hit[-1] if hit else min(reach, u_end)
        if nxt <= cur + 1e-6:
            break
        cur = min(nxt, u_end)
        out.append(cur)
    if out[-1] < u_end - 1e-6:
        out.append(u_end)
    # Огрызок уже целого листа не режут: если кусок уходит в мелочь, границу
    # убирают, а соседний лист доводят до края — лишь бы не длиннее листа.
    i = 1
    while i < len(out) - 1:
        if min(out[i] - out[i - 1], out[i + 1] - out[i]) < MIN_PIECE \
                and out[i + 1] - out[i - 1] <= sw + 1e-9:
            del out[i]
        else:
            i += 1
    return out


def _sheets(rect, sw: float, sh: float, u0: float, z0: float, stagger: float = 0.0):
    """Режет прямоугольник стены на листы sw x sh, ряды вразбежку.

    Сетка глобальная для всей стены, поэтому куски по разные стороны проёма
    остаются в одной раскладке, а не начинают раскрой заново.
    """
    import math
    a, b, c, e = rect
    out = []
    for k in range(math.floor((c - z0) / sh), math.ceil((e - z0) / sh)):
        rz1, rz2 = max(c, z0 + k * sh), min(e, z0 + (k + 1) * sh)
        if rz2 - rz1 < 1e-6:
            continue
        off = (k % 2) * stagger
        for j in range(math.floor((a - u0 - off) / sw), math.ceil((b - u0 - off) / sw)):
            ra, rb = max(a, u0 + off + j * sw), min(b, u0 + off + (j + 1) * sw)
            if rb - ra > 1e-6:
                out.append((ra, rb, rz1, rz2))
    return out


def _face_rects(u_lo: float, u_hi: float, z_lo: float, z_hi: float,
                holes: list[tuple[float, float, float, float]]
                ) -> list[tuple[float, float, float, float]]:
    """Прямоугольники плоскости стены за вычетом проёмов.

    Обшивки, плёнки и облицовка идут листом по всей стене, но окно и дверь
    они не перекрывают — лист вырезается по проёму.
    """
    holes = [h for h in holes if h[1] > u_lo and h[0] < u_hi and h[3] > z_lo and h[2] < z_hi]
    if not holes:
        return [(u_lo, u_hi, z_lo, z_hi)]
    edges = sorted({u_lo, u_hi}
                   | {min(max(h[i], u_lo), u_hi) for h in holes for i in (0, 1)})
    out = []
    for a, b in zip(edges, edges[1:]):
        if b - a < 1e-6:
            continue
        mid = (a + b) / 2
        spans = sorted((max(h[2], z_lo), min(h[3], z_hi))
                       for h in holes if h[0] < mid < h[1])
        cur = z_lo
        for p1, p2 in spans:
            if p1 > cur + 1e-6:
                out.append((a, b, cur, p1))
            cur = max(cur, p2)
        if z_hi - cur > 1e-6:
            out.append((a, b, cur, z_hi))
    return out


def _depth_layers(depth: float, layer: float) -> list[tuple[float, float]]:
    """Слои утеплителя по глубине каркаса, от наружной грани внутрь.

    Остаток тоньше 10 мм уходит в последний слой, чтобы не плодить фольгу.
    """
    if layer <= 0 or depth <= layer + 0.005:
        return [(0.0, depth)]
    out, z = [], 0.0
    while depth - z > layer + 0.005:
        out.append((z, z + layer))
        z += layer
    if depth - z < 0.01 and out:
        out[-1] = (out[-1][0], depth)
    else:
        out.append((z, depth))
    return out


def _plates(a: float, b: float, step: float, first: float = 0.0) -> list[tuple[float, float]]:
    """Делит ячейку по высоте на плиты step метров, снизу вверх.

    first — высота первой плиты (для укладки вразбежку); 0 — как все.
    Остаток ниже 100 мм не плодит обрезок, а добавляется к последней плите.
    """
    if step <= 0 or b - a <= step + 0.1:
        return [(a, b)]
    out, z = [], a
    if first > 0 and b - a > first + 0.1:
        out.append((a, a + first))
        z = a + first
    while b - z > step + 0.1:
        out.append((z, z + step))
        z += step
    out.append((z, b))
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
    # X-стены идут насквозь, значит их ВНУТРЕННИЕ слои нужно подрезать на углах,
    # чтобы не пересекаться со слоями поперечных стен
    ext_through = abs(d[1]) < 0.5
    # на сколько подрезать внутренние слои X-стен, чтобы не налезать на слои поперечных
    _th_int = _up(R.sheathing_min_thickness(sp, "gkl")) * MM
    _corner_clear = (depth + (0.002 if on["vapour_barrier"] else 0.0)
                     + (_th_int if on["wall_sheathing_int"] else 0.0)) if ext_through else 0.0
    add = res.members.append

    _lay0 = spec.get("layers") if isinstance(spec.get("layers"), dict) else {}
    _tapes: list = []
    _holes = [(op["u"], op["u"] + op["width"], z0 + op["sill"], z0 + op["head"])
              for op in wall.get("openings", [])]

    _sheet = sorted(float(v) for v in _lay0.get("sheet_mm", SHEET_MM))
    if _lay0.get("sheet_lay", SHEET_LAY) == "v":
        _sw, _sh = _sheet[0] * MM, _sheet[1] * MM
    else:
        _sw, _sh = _sheet[1] * MM, _sheet[0] * MM
    _si = sorted(float(v) for v in _lay0.get("sheet_int_mm", SHEET_INT_MM))
    if _lay0.get("sheet_int_lay", SHEET_INT_LAY) == "v":
        _siw, _sih = _si[0] * MM, _si[1] * MM
    else:
        _siw, _sih = _si[1] * MM, _si[0] * MM
    _si_stag = bool(_lay0.get("sheet_int_stagger", SHEET_INT_STAGGER))
    _roll = _lay0.get("roll_mm", ROLL_MM)
    _rw, _rlap = float(_roll[0]) * MM, float(_roll[1]) * MM

    def slab(kind, label, thick_mm, offset, zc, h, note, length=None, inset=0.0,
             wrap=False, sheet=False, roll=False, col=None, mat=None,
             cfg=None, tape=False):
        """Плита по стене: offset — от наружной грани внутрь (+) / наружу (−).

        Режется по проёмам: окно и дверь обшивка и плёнки не перекрывают.
        wrap — завернуть на угол. Каркас Y-стен короче на толщину X-стен, и без
        этого наружные слои не доходят до угла: остаётся полоса голого каркаса,
        а для водовоздухозащитного слоя это ещё и разрыв вопреки 9.3.1.4.
        """
        thick_mm = _up(thick_mm)
        half = thick_mm * MM / 2
        c = offset + half
        lap = (depth - offset) if (wrap and ext and not ext_through and offset < 0) else 0.0
        u_a, u_b = inset - lap, (length or L) - inset + lap
        rects = _face_rects(u_a, u_b, zc - h / 2, zc + h / 2, _holes)
        sw, sh, stag = cfg or (_sw, _sh, True)
        if sheet and sw > 0 and sh > 0:
            import math
            z_lo, z_hi = zc - h / 2, zc + h / 2
            nrow = max(1, math.ceil((z_hi - z_lo) / sh - 1e-9))
            bands = {}
            for ra, rb, rz1, rz2 in rects:
                for k in range(nrow):
                    ba = z_lo + k * sh
                    bb = min(z_lo + (k + 1) * sh, z_hi)
                    ca, cb = max(rz1, ba), min(rz2, bb)
                    if cb - ca <= 1e-6:
                        continue
                    edges = _cols(ra, rb, sw, wall["stud_axes"],
                                  0.5 if (stag and k % 2) else 1.0)
                    for p, q in zip(edges, edges[1:]):
                        xa, xb = max(ra, p), min(rb, q)
                        if xb - xa > 1e-6:
                            bands.setdefault((round(ca, 6), round(cb, 6)), []).append([xa, xb])
            out = []
            for (ca, cb), band in bands.items():
                # Склейка по всему ряду, а не внутри полосы между проёмами:
                # край проёма режет лист не по стойке, и огрызок надо приклеить
                # к соседнему куску, даже если тот лежит за этой границей.
                band.sort()
                i = 1
                while i < len(band):
                    a0, b0 = band[i - 1]
                    a1, b1 = band[i]
                    if abs(a1 - b0) < 1e-6 \
                            and min(b0 - a0, b1 - a1) < MIN_PIECE \
                            and b1 - a0 <= sw + 1e-9:
                        band[i - 1][1] = b1
                        del band[i]
                    else:
                        i += 1
                out += [(xa, xb, ca, cb) for xa, xb in band]
            rects = out
        if roll and _rw > 0:
            z_lo, z_hi = zc - h / 2, zc + h / 2
            step = _rw - _rlap
            bands, zb, i = [], z_lo, 0
            while zb < z_hi - 1e-6:
                bands.append((zb, min(zb + _rw, z_hi), i))
                zb += step
                i += 1
            out = []
            for ra, rb, rz1, rz2 in rects:
                for ba, bb, bi in bands:
                    ca, cb = max(rz1, ba), min(rz2, bb)
                    if cb - ca > 1e-6:
                        out.append((ra, rb, ca, cb, bi))
            rects = out
            if tape:
                # шов — низ каждого полотнища, кроме самого нижнего
                for ra, rb, ca, cb, bi in rects:
                    if bi and abs(ca - bands[bi][0]) < 1e-6:
                        _tapes.append((ra, rb, ca, c - bi * 0.0002 - 0.0006))

        for rect in rects:
            ra, rb, rz1, rz2 = rect[:4]
            # полотнище кладётся поверх нижнего, поэтому каждое следующее на 0,2 мм
            # дальше наружу: иначе в зоне нахлёста два полотна в одной плоскости
            rc = c - (rect[4] * 0.0002 if len(rect) > 4 else 0.0)
            rzc, rh = (rz1 + rz2) / 2, rz2 - rz1
            p1 = (o[0] + d[0] * ra - n[0] * rc, o[1] + d[1] * ra - n[1] * rc, rzc)
            p2 = (o[0] + d[0] * rb - n[0] * rc, o[1] + d[1] * rb - n[1] * rc, rzc)
            add(Member(kind, label, (thick_mm, int(round(rh * 1000))),
                       p1, p2, n, col or group, note,
                       meta={"material": mat} if mat else {}))

    # --- наружная защитная обшивка каркаса ---
    mat_ext = _lay0.get("sheathing_ext_material", DEFAULT_SHEATHING_EXT)
    th_ext = 0.0
    if on["wall_sheathing_ext"] and ext:
        th = max(R.sheathing_min_thickness(sp, mat_ext), 9.5)
        th_ext = th * MM
        _mn = MATERIAL_NAMES.get(mat_ext, mat_ext)
        _extra = R.material_note(mat_ext)
        slab("sheathing_ext", f"Наружная обшивка {_mn} {th:g} мм", th, -th_ext,
             (z_bot + z_top) / 2, H,
             f"табл. 7-3 (жёсткость каркаса) и 10.4.4.2 (основание под облицовку); "
             f"≥9,5 мм также требуется для применения табл. Б-13 к перемычкам"
             + (". " + _extra if _extra else ""), wrap=True, sheet=True,
             col=G_SHEATHING_EXT, mat=mat_ext)

    # --- водовоздухозащитный слой (ветрозащита) ---
    if on["windproof"] and ext:
        _n_sheets = 1 if on["wall_sheathing_ext"] else 2
        _where = ("по наружной защитной обшивке" if on["wall_sheathing_ext"]
                  else "непосредственно по утеплителю")
        slab("windproof", f"Водовоздухозащитный слой ({_n_sheets} сл.)", 2,
             -(th_ext + 2 * MM), (z_bot + z_top) / 2, H,
             f"9.3.2.8: при наружной обшивке из материалов на древесной основе или без "
             f"обшивки слой обязателен. 9.3.2.9: {_where} — не менее {_n_sheets} сл.; "
             f"материал проницаем для водяного пара (полиолефин, перфорированный "
             f"полиэтилен), 9.3.2.10: паропроницаемость 0,61…5,0 мг/(Па·ч·м²). "
             f"9.3.3.2: стыки герметично или внахлёст ≥100 мм, крепить скобками "
             f"к каркасу или обрешётке. В модели показан условной толщиной 2 мм",
             wrap=True, roll=True, col=G_WINDPROOF, tape=True)

    # --- утеплитель в пустотах каркаса ---
    if on["wall_insulation"] if ext else on["interior_insulation"]:
        lay = spec.get("layers")
        plate = (float(lay.get("insulation_plate_mm", DEFAULT_PLATE_MM))
                 if isinstance(lay, dict) else DEFAULT_PLATE_MM) * MM
        label = "Утеплитель" if ext else "Звукоизоляция"
        note = ("9.2.2.2 «а»: в пространстве между стойками, обвязками и обшивками; "
                "λ ≤0,10 Вт/(м·°C) (9.2.2.1). Толщина = глубине каркаса, "
                "достаточность проверяется теплотехническим расчётом (9.2.1.2)" if ext else
                "7.5.2: звукоизоляция стен и перегородок внутри дома — по заданию на "
                "проектирование. Само заполнение ячеек СП не нормирует: табл. 7-6 даёт "
                "прибавку Iв только для обшивок и крепления к гибким профилям")
        layer = (float(lay.get("insulation_layer_mm", DEFAULT_LAYER_MM))
                 if isinstance(lay, dict) else DEFAULT_LAYER_MM) * MM
        cav = _cavities(wall)
        dl = _depth_layers(depth, layer)
        # Швы не выводят в один уровень: каждый следующий слой по глубине сдвинут
        # на долю плиты, и соседние ячейки — ещё на половину. Шов слоя приходится
        # на целое полотно соседнего, то есть перекрывается внахлёст.
        bays = sorted({c[0] for c in cav})
        for u1, u2, a, b in cav:
            bay = bays.index(u1) % 2
            for k, (d0, d1) in enumerate(dl):
                if on["insulation_stagger"]:
                    off = (plate * k / len(dl) + (plate / 2 if bay else 0.0)) % plate
                    first = off if off > 0.05 else 0.0
                else:
                    first = 0.0
                t_mm = int(round((d1 - d0) * 1000))
                c = (d0 + d1) / 2
                for z1, z2 in _plates(a, b, plate, first):
                    zc, h = (z1 + z2) / 2, z2 - z1
                    p1 = (o[0] + d[0] * u1 - n[0] * c, o[1] + d[1] * u1 - n[1] * c, zc)
                    p2 = (o[0] + d[0] * u2 - n[0] * c, o[1] + d[1] * u2 - n[1] * c, zc)
                    add(Member("insulation", f"{label} {t_mm} мм",
                               (t_mm, int(round(h * 1000))), p1, p2, n,
                               G_INSULATION, note))

    # --- пароизоляция с тёплой стороны ---
    if on["vapour_barrier"] and ext:
        slab("vapour", "Пароизоляция (плёнка ≥0,15 мм)", 2, depth, (z_bot + z_top) / 2, H,
             "9.3.2.2: полиэтиленовая плёнка ≥0,15 мм с тёплой стороны утеплителя; "
             "в модели показана условной толщиной 2 мм",
             inset=_corner_clear, roll=True, col=G_VAPOUR, tape=True)

    # --- внутренняя обшивка ---
    if on["wall_sheathing_int"]:
        th = R.sheathing_min_thickness(sp, "gkl")
        off = depth + (2 * MM if on["vapour_barrier"] and ext else 0.0)
        slab("sheathing_int", f"Внутренняя обшивка ГКЛ {th:g} мм", th, off,
             (z_bot + z_top) / 2, H,
             f"табл. 7-3: ГКЛ/ГВЛ ≥{th:g} мм при шаге стоек {sp} мм; "
             f"винты с шагом ≤300 мм (табл. 7-4), края листов над опорами (7.3.5.3)",
             inset=_corner_clear, sheet=True, col=G_SHEATHING_INT,
             cfg=(_siw, _sih, _si_stag))
        if not ext:
            slab("sheathing_int", f"Внутренняя обшивка ГКЛ {th:g} мм", th, -th * MM,
                 (z_bot + z_top) / 2, H, "7.3.1: перегородки обшиваются с обеих сторон",
                 sheet=True, col=G_SHEATHING_INT, cfg=(_siw, _sih, _si_stag))

    # --- лента по швам плёнок (10.2.2) ---
    _tw = float(_lay0.get("tape_mm", TAPE_MM)) * MM
    for ta, tb, tz, tc in _tapes:
        p1 = (o[0] + d[0] * ta - n[0] * tc, o[1] + d[1] * ta - n[1] * tc, tz)
        p2 = (o[0] + d[0] * tb - n[0] * tc, o[1] + d[1] * tb - n[1] * tc, tz)
        add(Member("tape", f"Лента по шву {int(round(_tw * 1000))} мм",
                   (1, int(round(_tw * 1000))), p1, p2, n, G_TAPE,
                   "10.2.2: все швы листов проклеиваются липкой лентой. Ширину ленты СП "
                   "не задаёт. Шов — нахлёст полотнищ ≥100 мм (9.3.3.2)"))

    # --- облицовка по обрешётке с вентзазором ---
    if on["cladding"] and ext:
        gap = R.CLEARANCES["masonry_veneer_gap_recommended"] * MM   # 38 мм
        base = th_ext + (2 * MM if on["windproof"] else 0.0)
        bt, bh = (19, 38)
        for u in wall["stud_axes"]:
            c = -(base + gap / 2)
            p1 = (o[0] + d[0] * u - n[0] * c, o[1] + d[1] * u - n[1] * c, z0)
            p2 = (o[0] + d[0] * u - n[0] * c, o[1] + d[1] * u - n[1] * c, z1)
            add(Member("batten", f"Обрешётка {bt}x{bh}", (bh, bt), p1, p2, d, G_CLADDING,
                       "10.4.4.3: обрешётка ≥19x38 мм по каркасу; при креплении прямо к стойкам "
                       "≥19x65 мм при шаге 400 и ≥19x89 мм при шаге 600 (10.4.4.4)"))
        slab("cladding", "Облицовка 20 мм", 20, -(base + gap + 0.020),
             (z_bot + z_top) / 2, H,
             "10.3.2.2: зазор между облицовкой и обшивкой ≥25 мм, рекомендуется 38 мм; "
             "низ деревянной облицовки ≥250 мм над планировкой (5.4.7)", wrap=True,
             col=G_CLADDING)


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
                   (L, W / 2, z_joist_bottom + t_mm * MM / 2), (0, 0, 1), G_INSULATION_ATTIC,
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
                   (0, W / 2, z), (L, W / 2, z), (0, 0, 1), G_INSULATION_ATTIC,
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
