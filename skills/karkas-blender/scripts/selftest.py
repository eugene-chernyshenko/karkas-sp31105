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
eq(R.subfloor_min_thickness(600, "osb"), 26.0, "6-2 ДСП при шаге 600")
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
                   "openings": [{"wall": "S", "u": 1.2, "width": 1.5, "height": 1.5,
                                 "sill": 0.9}]})
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
