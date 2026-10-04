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

if fails:
    print("ПРОВАЛЕНО:")
    for f in fails:
        print("  ✗", f)
    sys.exit(1)
print(f"OK — все проверки пройдены ({len(res.members)} элементов в эталонной модели)")
