#!/usr/bin/env python3
"""Самопроверка: таблицы СП + генератор. Запуск: python3 scripts/selftest.py"""
from __future__ import annotations
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from karkas import rules as R                      # noqa: E402
from karkas.model import build_house, bom          # noqa: E402

fails = []


def eq(got, want, what):
    if got != want:
        fails.append(f"{what}: получено {got!r}, ожидалось {want!r}")


def true(cond, what):
    if not cond:
        fails.append(what)


# --- контрольные значения прямо из таблиц Приложения Б ---
eq(R.joist_max_span("38x235", 400, table="B1", bracing="hv"), 4.29, "Б-1 38x235@400 hv")
eq(R.joist_max_span("38x286", 600, table="B2", bracing="screed"), 4.79, "Б-2 38x286@600 стяжка")
eq(R.joist_max_span("38x184", 300, table="B3"), 6.44, "Б-3 38x184@300")
eq(R.roof_beam_max_span("38x140", 400, 2.0), 2.80, "Б-4 38x140@400 снег 2,0")
eq(R.roof_beam_max_span("38x235", 600, 3.0), 3.59, "Б-5 38x235@600 снег 3,0")
eq(R.rafter_max_span("38x286", 300, 1.0), 10.00, "Б-6 38x286@300 снег 1,0")
eq(R.rafter_max_span("38x184", 600, 2.5), 3.52, "Б-7 38x184@600 снег 2,5")
eq(R.girder_max_span("4x235", 4.8, 1), 3.24, "Б-8 4х(38x235) B=4,8")
eq(R.girder_max_span("3x184", 6.0, 3), 1.15, "Б-10 3х(38x184) B=6,0, 3 этажа")
eq(R.ridge_beam_max_span("5x286", 2.0, 4.9), 3.69, "Б-11 5х(38x286) снег 2,0")
eq(R.ridge_beam_max_span("5x286", 2.0, 3.5), round(3.69 * 1.10, 3), "Б-11 +10 % при B≤3,7")
eq(R.lintel_max_span(184, "roof+1", snow_kpa=1.5, sheathed=False), 1.67, "Б-12 2х(38x184) +1 этаж")
eq(R.lintel_max_span(235, "roof", snow_kpa=1.0, sheathed=True), 3.36, "Б-13 2х(38x235) крыша")
eq(R.lintel_max_span(140, "roof", wall="internal"), 1.35, "Б-12 внутренняя стена 2х(38x140)")
eq(R.T_B14["4x286"][0], 4.92, "Б-14 4х(38x286) снег 1,0")

# интерполяция по грузовой площади (середина между 3,0 и 3,6)
eq(R.girder_max_span("3x184", 3.3, 1), round((2.90 + 2.65) / 2, 3), "Б-8 интерполяция B=3,3")

# округление снега вверх до табличной колонки
eq(R.rafter_max_span("38x140", 600, 1.2), R.rafter_max_span("38x140", 600, 1.5),
   "снег 1,2 кПа -> колонка 1,5")

# --- таблица 7-1 ---
true(R.check_stud("38x89", 600, 3.0, "external", "attic")[0], "7-1: 38x89@600 чердак — должно пройти")
true(not R.check_stud("38x89", 600, 3.0, "external", "attic+1")[0],
     "7-1: 38x89@600 чердак+1 этаж — должно НЕ пройти")
true(R.check_stud("38x140", 600, 3.0, "external", "attic+1")[0],
     "7-1: 38x140@600 чердак+1 — должно пройти (не слабее 38x140@600)")
true(R.check_stud("38x184", 600, 3.0, "external", "attic")[0],
     "7-1: сечение крупнее табличного должно проходить")
true(not R.check_stud("38x64", 600, 2.4, "external", "attic")[0],
     "7-1: 38x64 допускается только при шаге ≤400")

# --- прочие таблицы ---
eq(R.subfloor_min_thickness(600, "dsp"), 26.0, "6-2 ДСП при шаге 600")
eq(R.subfloor_min_thickness(600, "osb"), 18.0, "6-2: ОСП в таблице нет, считается по фанере")
eq(R.sheathing_min_thickness(400, "gkl"), 10.0, "7-3 ГКЛ при шаге 400")
eq(R.roof_deck_min_thickness(600, "lumber"), 19.0, "8-6 пиломатериал при шаге 600")
eq(R.foundation(3)["ext_mm"], 450, "5-1 лента, 3 этажа")
eq(R.foundation(2, masonry_veneer=True)["ext_mm"], 350 + 130, "5-1 + облицовка кладкой")
eq(R.rafter_tie_nails("1:2", 600, 2.0), 8, "8-1 уклон 1:2, шаг 600, снег 2,0")
eq(R.rafter_tie_nails("1:3", 600, 1.5), None, "8-1: сочетание не допускается")

# --- подбор ---
eq(R.pick_joist(3.5, 400), "38x184", "подбор балки на 3,5 м @400")
eq(R.pick_rafter(4.4, 600, 1.5), "38x184", "подбор стропила 4,4 м @600 снег 1,5")
eq(R.pick_lintel(1.5, "roof", snow_kpa=1.5, sheathed=True), 140, "подбор перемычки 1,5 м")

# --- генератор ---
res = build_house({"plan": {"length": 9.0, "width": 7.0}, "snow_kpa": 1.5,
                   "ext_stud": "38x140",
                   "interior_walls": [{"axis": "x", "pos": 3.5, "bearing": True}],
                   "openings": [{"wall": "S", "u": 1.2, "width": 1.5, "height": 1.4,
                                 "sill": 0.8}]})
true(not res.errors, f"эталонный дом должен проходить без ✗: {res.errors}")
true(len(res.members) > 200, f"слишком мало элементов: {len(res.members)}")
kinds = {m.kind for m in res.members}
for k in ("stud", "plate", "header", "joist", "rim", "rafter", "ceiling_joist", "ridge",
          "gable_stud", "sill_plate", "subfloor", "foundation"):
    true(k in kinds, f"в модели нет элементов типа {k}")
true(all(m.length > 0 for m in res.members), "есть элементы нулевой/отрицательной длины")
true(sum(r["volume_m3"] for r in bom(res.members)) > 3.0, "подозрительно малый объём древесины")

# нарушения должны выявляться
bad = build_house({"plan": {"length": 9.0, "width": 12.0}, "snow_kpa": 3.0, "storeys": 3})
true(bad.errors, "дом шириной 12 м при снеге 3,0 кПа должен давать ✗")

# --- геометрия каркаса: элементы не должны пересекаться и выходить за габариты ---
import itertools


def _aabb(m):
    ax, wv, hv = m.basis
    c, half = m.center, [0.0, 0.0, 0.0]
    for v, sz in ((ax, m.length), (wv, m.section[0] / 1000), (hv, m.section[1] / 1000)):
        for i in range(3):
            half[i] += abs(v[i]) * sz / 2
    return [(c[i] - half[i], c[i] + half[i]) for i in range(3)]


def collisions(members, min_vol=1e-7):
    boxes = [(m, _aabb(m)) for m in members]
    out = []
    for (m1, b1), (m2, b2) in itertools.combinations(boxes, 2):
        ov = [min(b1[i][1], b2[i][1]) - max(b1[i][0], b2[i][0]) for i in range(3)]
        if all(o > 2e-4 for o in ov) and ov[0] * ov[1] * ov[2] > min_vol:
            out.append((m1.label, m2.label, ov[0] * ov[1] * ov[2]))
    return out


_geo = build_house({"plan": {"length": 6.0, "width": 6.0}, "ext_stud": "38x140",
                    "interior_walls": [{"axis": "x", "pos": 3.0, "bearing": True}],
                    "openings": [
                        {"wall": "S", "u": 0.8, "width": 1.5, "height": 1.4, "sill": 0.8},
                        {"wall": "S", "u": 3.0, "width": 1.0, "height": 2.1, "type": "door"},
                        {"wall": "W", "u": 0.8, "width": 1.2, "height": 1.4,
                         "sill": 0.8}]})   # не 2.2: перегородка pos=3.0 придёт в проём
true(not _geo.errors, f"контрольный дом для геометрии даёт ✗: {_geo.errors}")
_walls = [m for m in _geo.members
          if m.group in ("02_Стены_1", "03_Внутренние_стены")]
_col = collisions(_walls)
true(not _col, "элементы стен пересекаются по объёму: "
               + "; ".join(f"{a[:34]} ∩ {b[:34]} ({v * 1e6:.0f} см³)" for a, b, v in _col[:4]))
for m in _walls:
    bb = _aabb(m)
    true(bb[0][0] > -1e-3 and bb[0][1] < 6.0 + 1e-3
         and bb[1][0] > -1e-3 and bb[1][1] < 6.0 + 1e-3,
         f"элемент стены вне габаритов плана: {m.label}")

# перемычка должна стоять НА РЕБРО: высота сечения больше толщины по вертикали (7.2.14)
_hdr = next(m for m in _geo.members if m.kind == "header")
_hb = _aabb(_hdr)
true((_hb[2][1] - _hb[2][0]) > (_hb[0][1] - _hb[0][0]) * 0 + 0.08,
     "7.2.14: перемычка должна быть поставлена на ребро (высота сечения — по вертикали)")

# проём не помещается по высоте -> должно быть ✗
_tall = build_house({"plan": {"length": 6.0, "width": 6.0}, "wall_height": 2.5,
                     "openings": [{"wall": "S", "u": 1.0, "width": 1.5,
                                   "height": 1.5, "sill": 0.9}]})   # верх 2,40 + 140 > 2,50
true(any("не помещается под верхнюю обвязку" in f[2] and f[0] == "ERR"
         for f in _tall.findings),
     "перемычка выше свободной высоты стойки должна давать ✗")

# проём у самого края стены -> должно быть ✗ (7.2.13)
_edge = build_house({"plan": {"length": 6.0, "width": 6.0},
                     "openings": [{"wall": "S", "u": 0.02, "width": 1.0,
                                   "height": 1.4, "sill": 0.8}]})
true(any("7.2.13" in f[2] and f[0] == "ERR" for f in _edge.findings),
     "проём вплотную к углу должен давать ✗ (нет места под двойные стойки)")

# слои оболочки не должны пересекаться с каркасом и друг с другом
_geo_l = build_house({"plan": {"length": 9.0, "width": 7.0}, "ext_stud": "38x140",
                      "layers": "all",
                      "openings": [{"wall": "S", "u": 1.0, "width": 1.5,
                                    "height": 1.4, "sill": 0.8},
                                   {"wall": "S", "u": 4.0, "width": 1.0,
                                    "height": 2.1, "type": "door"}],
                      "interior_walls": [{"axis": "x", "pos": 3.5, "bearing": True}]})
_cl = collisions([m for m in _geo_l.members if "Стены" in m.group])
true(not _cl, "слои оболочки пересекаются с каркасом: "
              + "; ".join(f"{a[:32]} ∩ {b[:32]}" for a, b, _ in _cl[:4]))

# --- 7.2.10: нахлёст досок верхней обвязки в углах и пересечениях ---
lap = build_house({"plan": {"length": 6.0, "width": 6.0}, "ext_stud": "38x140",
                   "interior_walls": [{"axis": "x", "pos": 3.0, "bearing": True}]})
t_ext = 0.140


def _plate(level, tag):
    return [m for m in lap.members if m.kind == "plate"
            and f"Верхняя обвязка {level}" in m.label and tag in m.label]


# нижние доски: X-стены проходят насквозь, Y-стены упираются встык
sx = _plate(1, "наружная S")[0]
true(abs(min(sx.p1[0], sx.p2[0])) < 1e-6 and abs(max(sx.p1[0], sx.p2[0]) - 6.0) < 1e-6,
     "7.2.10: нижняя доска обвязки X-стены должна идти на всю длину")
wl = _plate(1, "наружная W")[0]
true(abs(min(wl.p1[1], wl.p2[1]) - t_ext) < 1e-6,
     "7.2.10: нижняя доска обвязки Y-стены должна упираться встык (отступ на толщину стены)")
# верхние доски: наоборот — Y-стены перекрывают стык в углу
wu = _plate(2, "наружная W")
true(abs(min(min(m.p1[1], m.p2[1]) for m in wu)) < 1e-6,
     "7.2.10: верхняя доска Y-стены должна доходить до наружной грани угла (перекрывать стык)")
su = _plate(2, "наружная S")[0]
true(abs(min(su.p1[0], su.p2[0]) - t_ext) < 1e-6,
     "7.2.10: верхняя доска X-стены должна отступать на толщину стены в углу")
# пересечение: верхняя доска наружной стены разрезана, внутренняя заходит внутрь
true(len(wu) == 2, "7.2.10: верхняя доска наружной стены должна прерываться на "
                   "пересечении с внутренней несущей стеной")
iu = _plate(2, "внутренняя 1")[0]
true(abs(min(iu.p1[0], iu.p2[0])) < 1e-6 and abs(max(iu.p1[0], iu.p2[0]) - 6.0) < 1e-6,
     "7.2.10: верхняя доска внутренней несущей стены должна заходить в наружные стены")
il = _plate(1, "внутренняя 1")[0]
true(abs(min(il.p1[0], il.p2[0]) - t_ext) < 1e-6,
     "7.2.10: нижняя доска внутренней стены должна упираться встык")

# --- новые конструкции ---
hip = build_house({"plan": {"length": 11.0, "width": 8.0}, "snow_kpa": 1.5,
                   "ext_stud": "38x140", "roof": {"type": "hip", "slope": "1:2"},
                   "interior_walls": [{"axis": "x", "pos": 4.0, "bearing": True}]})
true(not hip.errors, f"вальмовая крыша должна проходить без ✗: {hip.errors}")
hk = {m.kind for m in hip.members}
for k in ("hip_rafter", "jack_rafter", "ridge"):
    true(k in hk, f"вальмовая крыша: нет элементов {k}")
true(sum(1 for m in hip.members if m.kind == "hip_rafter") == 4,
     "вальмовая крыша: должно быть ровно 4 накосных стропила")
true(any("накосн" in f[2] and f[0] == "WARN" for f in hip.findings),
     "вальма: должно быть предупреждение, что пролёт накосных таблицами не нормируется")
eq(hip.picked["hip_rafter"], "38x235", "8.2.1.8: накосное на ≥50 мм выше рядового 38x184")

# пирамидальная (шатровая) крыша
pyr = build_house({"plan": {"length": 8.0, "width": 8.0}, "ext_stud": "38x140",
                   "roof": {"type": "hip", "slope": "1:2"},
                   "interior_walls": [{"axis": "x", "pos": 4.0, "bearing": True}]})
true(not pyr.errors, f"шатровая крыша должна проходить без ✗: {pyr.errors}")

# мансардные (опорные) стенки сокращают пролёт стропил
kn = build_house({"plan": {"length": 9.0, "width": 8.0}, "ext_stud": "38x140",
                  "roof": {"slope": "1:1.33", "attic": "living",
                           "knee_walls": {"offset": 1.6}}})
true(not kn.errors, f"мансардные стенки: {kn.errors}")
true(any("опорные стенки" in f[2] for f in kn.findings), "нет записи об опорных стенках")
eq(kn.picked["rafter"], "38x140", "с опорной стенкой пролёт 2,40 м -> 38x140")

# проёмы в перекрытии 6.2.11
fo = build_house({"plan": {"length": 9.0, "width": 7.0}, "ext_stud": "38x140",
                  "floor_openings": [{"x0": 1.0, "y0": 1.0, "x1": 2.4, "y1": 2.0}],
                  "interior_walls": [{"axis": "x", "pos": 3.5, "bearing": True}]})
true(any(m.kind == "trimmer" for m in fo.members), "нет обрамления проёма в перекрытии")
true(any("1,2 м" in f[2] for f in fo.findings), "6.2.11.1: не сработало правило >1,2 м")
big = build_house({"plan": {"length": 9.0, "width": 7.0}, "ext_stud": "38x140",
                   "floor_openings": [{"x0": 1.0, "y0": 1.0, "x1": 2.0, "y1": 4.5}]})
true(any("6.2.11.2" in f[2] and f[0] == "ERR" for f in big.findings),
     "проём шириной 3,5 м вдоль балок должен давать ✗ по 6.2.11.2")

# консоли 6.2.10
cv = build_house({"plan": {"length": 9.0, "width": 7.0}, "ext_stud": "38x140",
                  "cantilevers": [{"side": "S", "overhang": 0.5}],
                  "interior_walls": [{"axis": "x", "pos": 3.5, "bearing": True}]})
true(any("6.2.10.1" in f[2] for f in cv.findings), "не сработало правило 6.2.10.1")
cv2 = build_house({"plan": {"length": 9.0, "width": 7.0},
                   "cantilevers": [{"side": "S", "overhang": 0.9}]})
true(any("600 мм" in f[2] and f[0] == "ERR" for f in cv2.findings),
     "вылет 900 мм должен давать ✗ (6.2.10.1)")

# лестница, раздел 12
stc = build_house({"plan": {"length": 9.0, "width": 7.0}, "storeys": 2,
                   "int_stud": "38x140", "ext_stud": "38x140",
                   "floor_openings": [{"x0": 1.7, "y0": 1.0, "x1": 4.6, "y1": 2.1}],
                   "stairs": {"x": 1.0, "y": 1.0, "dir": "x", "width": 1.0},
                   "interior_walls": [{"axis": "x", "pos": 3.5, "bearing": True,
                                       "spacing": 400}]})
true(not stc.errors, f"лестница: {stc.errors}")
true(any(m.kind == "tread" for m in stc.members), "нет ступеней")
true(any("косоур" in f[2] for f in stc.findings),
     "нет оговорки, что сечение косоуров СП не нормирует")
true(any("12.2.1.3" in f[2] for f in stc.findings),
     "лестница: не посчитана требуемая длина проёма по высоте в свету")
narrow = build_house({"plan": {"length": 9.0, "width": 7.0}, "storeys": 2,
                      "stairs": {"x": 1.0, "y": 1.0, "dir": "x", "width": 0.8}})
true(any("900 мм" in f[2] and f[0] == "ERR" for f in narrow.findings),
     "лестница шириной 800 мм должна давать ✗ (12.2.1.1)")

# слои оболочки
lay = build_house({"plan": {"length": 9.0, "width": 7.0}, "ext_stud": "38x140",
                   "layers": "all",
                   "interior_walls": [{"axis": "x", "pos": 3.5, "bearing": True}]})
lk = {m.kind for m in lay.members}
for k in ("sheathing_ext", "sheathing_int", "insulation", "vapour", "cladding",
          "batten", "ceiling", "roof_deck"):
    true(k in lk, f"слой {k} не построен при layers='all'")
true(any("теплотехнич" in f[2] and f[0] == "WARN" for f in lay.findings),
     "нет предупреждения, что толщина утеплителя требует расчёта")
# 9.3.2.8: ветрозащита и материал наружной обшивки
_base = {"plan": {"length": 6.0, "width": 6.0}, "ext_stud": "38x140"}
_osb = build_house({**_base, "layers": {"wall_insulation": True,
                                        "wall_sheathing_ext": True}})
true(any(f[0] == "WARN" and "водовоздухозащитный" in f[1] for f in _osb.findings),
     "обшивка ОСП без ветрозащиты — должно быть ! по 9.3.2.8")
true(any(f[0] == "WARN" and "ОСП" in f[2] for f in _osb.findings),
     "ОСП нет в СП 31-105-2002 — это должно быть сказано явно")
_bare = build_house({**_base, "layers": {"wall_insulation": True}})
true(any(f[0] == "WARN" and "обшивки нет" in f[2] for f in _bare.findings),
     "без наружной обшивки ветрозащита обязательна по 9.3.2.8 — нет !")
_wp = build_house({**_base, "layers": {"wall_insulation": True, "windproof": True,
                                       "wall_sheathing_ext": True}})
true(not any("водовоздухозащитный" in f[1] and f[0] == "WARN" for f in _wp.findings),
     "ветрозащита включена, а ! всё равно выдан")
true(any(m.kind == "windproof" for m in _wp.members), "слой windproof не построен")
_csp = build_house({**_base, "layers": {"wall_insulation": True, "wall_sheathing_ext": True,
                                        "sheathing_ext_material": "csp"}})
true(not any("водовоздухозащитный" in f[1] and f[0] == "WARN" for f in _csp.findings),
     "ЦСП не на древесной основе — ! по 9.3.2.8 лишний")
eq(R.sheathing_min_thickness(600, "osb"), R.sheathing_min_thickness(600, "plywood"),
   "ОСП пока считается по строке фанеры (в СП 31-105-2002 ОСП нет)")

# 7.2.12: перегородка не должна приходить в проём несущей стены
_win = {"wall": "W", "u": 2.2, "width": 1.2, "height": 1.5, "sill": 0.8, "type": "window"}
_hit = build_house({"plan": {"length": 6.0, "width": 6.0}, "openings": [_win],
                    "interior_walls": [{"axis": "x", "pos": 3.0, "bearing": True}]})
true(any(f[0] == "ERR" and "примыкание к W" in f[1] for f in _hit.findings),
     "перегородка пришла в окно стены W, а ✗ не выдан (7.2.12)")
_ok = build_house({"plan": {"length": 6.0, "width": 6.0},
                   "openings": [dict(_win, u=0.8)],
                   "interior_walls": [{"axis": "x", "pos": 3.0, "bearing": True}]})
true(not any("примыкание" in f[1] for f in _ok.findings),
     "окно отодвинуто от примыкания, а ✗ всё равно выдан")
# перегородка, не доходящая до наружной стены, примыканием не считается
_short = build_house({"plan": {"length": 6.0, "width": 6.0}, "openings": [_win],
                      "interior_walls": [{"axis": "x", "pos": 3.0, "from": 2.0,
                                          "to": 4.0, "bearing": False}]})
true(not any("примыкание" in f[1] for f in _short.findings),
     "перегородка не доходит до стены W — примыкания нет, ✗ лишний")

# утеплитель: проёмы, слои по глубине, смещение швов, перегородки
ins = build_house({"plan": {"length": 6.0, "width": 6.0}, "ext_stud": "38x140",
                   "wall_height": 2.5,
                   "layers": {"wall_insulation": True, "interior_insulation": True,
                              "insulation_layer_mm": 50, "insulation_plate_mm": 1000},
                   "interior_walls": [{"axis": "x", "pos": 3.0, "bearing": True}],
                   "openings": [{"wall": "S", "u": 0.8, "width": 1.5, "height": 1.5,
                                 "sill": 0.8, "type": "window"}]})
_i = [m for m in ins.members if m.kind == "insulation"]
true(_i, "утеплитель стен не построен")

# 1) проём не заполняется: окно S u 0.8..2.3, низ проёма = верх обвязки + 0.8
_z0 = ins.levels["floor_1"] + 0.038
_box = (0.8, 2.3, _z0 + 0.8, _z0 + 2.3)
_hit = []
for m in _i:
    if abs(m.p1[1] - m.p2[1]) > 1e-6 or m.p1[1] > 0.2:   # только стена S
        continue
    u1, u2 = sorted((m.p1[0], m.p2[0]))
    h = m.section[1] / 1000.0
    z1, z2 = m.p1[2] - h / 2, m.p1[2] + h / 2
    if min(u2, _box[1]) - max(u1, _box[0]) > 1e-6 and min(z2, _box[3]) - max(z1, _box[2]) > 1e-6:
        _hit.append((round(u1, 3), round(z1, 3)))
true(not _hit, f"утеплитель лезет в проём окна (9.2.3.2 тут ни при чём): {_hit[:3]}")

# 2) глубина 140 мм набирается слоями 50+50+40, а не одним куском
_th = sorted({m.section[0] for m in _i if m.label.startswith("Утеплитель")})
eq(_th, [40, 50], "утеплитель 140 мм должен набираться слоями 50+50+40")
true(any(f[0] == "WARN" and "не делится на плиту" in f[2] for f in ins.findings),
     "нет ! о том, что 140 мм не делится на плиту 50 мм нацело")

# 3) швы слоёв разведены: в одной ячейке стыки разных слоёв не совпадают
_cell = [m for m in _i if abs(m.p1[0] - 4.219) < 1e-3 and m.p1[1] < 0.2]
_seams = {}
for m in _cell:
    h = m.section[1] / 1000.0
    _seams.setdefault(round(m.p1[1], 4), []).append(round(m.p1[2] + h / 2, 3))
_tops = [sorted(v)[:-1] for v in _seams.values()]
true(len(_seams) >= 2, "в ячейке должно быть несколько слоёв по глубине")
true(len({tuple(t) for t in _tops if t}) == len([t for t in _tops if t]),
     f"швы слоёв совпали по высоте — нет укладки внахлёст: {_tops}")

# 4) перегородка заполняется отдельным слоем и подписана звукоизоляцией
true(any(m.label.startswith("Звукоизоляция") for m in ins.members),
     "interior_insulation не заполнил внутреннюю стену")
true(all("7.5.2" in m.note for m in ins.members
         if m.label.startswith("Звукоизоляция")),
     "звукоизоляция перегородки должна ссылаться на 7.5.2")

# 5) утеплитель — свой слой и своя ведомость, не вперемешку с пиломатериалом
true({m.group for m in _i} <= {"11_Утеплитель_стен", "12_Утеплитель_чердака"},
     "утеплитель должен лежать в своих коллекциях, а не в слоях стен и крыши")
_mats = {r["material"] for r in bom(ins.members)}
true("утеплитель" in _mats and "пиломатериал" in _mats,
     "ведомость не разделяет утеплитель и пиломатериал")
true(not any(r["material"] == "утеплитель" for r in bom(ins.members, "пиломатериал")),
     "утеплитель попал в ведомость пиломатериалов")

plain = build_house({"plan": {"length": 9.0, "width": 7.0}, "ext_stud": "38x140"})
true(not any(m.kind in ("insulation", "cladding") for m in plain.members),
     "по умолчанию слои оболочки строиться не должны")

if fails:
    print("ПРОВАЛЕНО:")
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print(f"OK — все проверки пройдены ({len(res.members)} элементов в эталонной модели, "
      f"{len(hip.members)} в вальмовой, {len(lay.members)} со всеми слоями)")
