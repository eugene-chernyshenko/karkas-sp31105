"""Проёмы в перекрытии (6.2.11), консольные балки (6.2.10), лестницы (раздел 12)."""
from __future__ import annotations

import math

from . import rules as R
from .geom import Member

MM = 1 / 1000.0


# --------------------------------------------------------------------------
# 6.2.11 Проёмы в перекрытии
# --------------------------------------------------------------------------
def floor_openings(res, spec: dict, plat: dict, group: str,
                   openings: list[dict], label: str = "перекрытие") -> list[dict]:
    """Обрамление проёмов. Проём: {"x0","y0","x1","y1"} в плане, м.

    По 6.2.11 «длина» проёма меряется ПЕРПЕНДИКУЛЯРНО балкам, «ширина» — ПАРАЛЛЕЛЬНО.
    Возвращает список обработанных проёмов с рассчитанной геометрией.
    """
    if not openings:
        return []
    direction = spec["floor"]["direction"]          # 'y' — балки вдоль Y
    jt, jd = R.sec(plat["joist"])
    zc = plat["z_top"] - plat["subfloor_mm"] * MM - plat["depth"] / 2
    add = res.members.append
    done = []

    for i, op in enumerate(openings, 1):
        x0, y0 = min(op["x0"], op["x1"]), min(op["y0"], op["y1"])
        x1, y1 = max(op["x0"], op["x1"]), max(op["y0"], op["y1"])
        if direction == "y":
            along = y1 - y0          # вдоль балок = «ширина» по СП
            across = x1 - x0         # поперёк балок = «длина» по СП
        else:
            along = x1 - x0
            across = y1 - y0
        tag = f"{label}/проём {i}"

        # «длина» (перпендикулярно балкам) — балки по сторонам в этом направлении
        if across > 3.2:
            res.err(tag, f"длина проёма {across:.2f} м > 3,2 м — сечение ограничивающих "
                         f"балок определяется расчётом (6.2.11.1)")
        double_trim = across > 1.2
        if double_trim:
            res.ok(tag, f"длина проёма {across:.2f} м > 1,2 м — ограничивающие балки "
                        f"сдвоенные (6.2.11.1)")
        # «ширина» (параллельно балкам) — поперечные (ригельные) балки
        if along > 2.0:
            res.err(tag, f"ширина проёма {along:.2f} м > 2,0 м — сечение ограничивающих "
                         f"балок определяется расчётом (6.2.11.2)")
        double_head = along > 0.8
        if double_head:
            res.ok(tag, f"ширина проёма {along:.2f} м > 0,8 м — ограничивающие балки "
                        f"сдвоенные (6.2.11.2)")

        t = jt * MM
        n_trim = 2 if double_trim else 1
        n_head = 2 if double_head else 1

        # продольные (вдоль балок) — по сторонам проёма
        for side, base in ((0, (x0 if direction == "y" else y0)),
                           (1, (x1 if direction == "y" else y1))):
            for k in range(n_trim):
                off = -(k + 0.5) * t if side == 0 else (k + 0.5) * t
                c = base + off
                if direction == "y":
                    p1, p2 = (c, 0.0, zc), (c, spec["plan"]["width"], zc)
                else:
                    p1, p2 = (0.0, c, zc), (spec["plan"]["length"], c, zc)
                add(Member("trimmer", f"Балка у проёма {plat['joist']}"
                                      + (" (сдвоенная)" if double_trim else ""),
                           (jt, jd), p1, p2, (0, 0, 1), group,
                           "6.2.11.1: при длине проёма >1,2 м ограничивающие балки двойные"))

        # поперечные (ригели) — по торцам проёма
        for side, base in ((0, (y0 if direction == "y" else x0)),
                           (1, (y1 if direction == "y" else x1))):
            for k in range(n_head):
                off = -(k + 0.5) * t if side == 0 else (k + 0.5) * t
                c = base + off
                if direction == "y":
                    p1, p2 = (x0 - n_trim * t, c, zc), (x1 + n_trim * t, c, zc)
                else:
                    p1, p2 = (c, y0 - n_trim * t, zc), (c, y1 + n_trim * t, zc)
                add(Member("trimmer", f"Ригель проёма {plat['joist']}"
                                      + (" (сдвоенный)" if double_head else ""),
                           (jt, jd), p1, p2, (0, 0, 1), group,
                           "6.2.11.2: при ширине проёма >0,8 м ограничивающие балки двойные; "
                           "укороченные балки — на металлические уголки или гвозди по табл. 6-1"))
        done.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                     "across": across, "along": along, "zc": zc})
    return done


def suppress_joists_in_openings(res, openings: list[dict], spec: dict) -> int:
    """Убирает участки балок, попавшие в проёмы перекрытия, укорачивая их до обрамления."""
    if not openings:
        return 0
    direction = spec["floor"]["direction"]
    keep, removed = [], 0
    for m in res.members:
        if m.kind != "joist":
            keep.append(m)
            continue
        cut = None
        for op in openings:
            if direction == "y":
                inside = op["x0"] - 1e-6 < m.p1[0] < op["x1"] + 1e-6
                lo, hi = op["y0"], op["y1"]
                a, b = min(m.p1[1], m.p2[1]), max(m.p1[1], m.p2[1])
            else:
                inside = op["y0"] - 1e-6 < m.p1[1] < op["y1"] + 1e-6
                lo, hi = op["x0"], op["x1"]
                a, b = min(m.p1[0], m.p2[0]), max(m.p1[0], m.p2[0])
            if inside and not (b <= lo or a >= hi):
                cut = (max(a, lo), min(b, hi), a, b, lo, hi)
                break
        if cut is None:
            keep.append(m)
            continue
        removed += 1
        _, _, a, b, lo, hi = cut
        ax = 1 if direction == "y" else 0
        for s, e in ((a, lo), (hi, b)):
            if e - s < 0.15:
                continue
            p1 = list(m.p1); p2 = list(m.p2)
            p1[ax], p2[ax] = s, e
            keep.append(Member("joist", m.label + " (укороченная у проёма)", m.section,
                               tuple(p1), tuple(p2), m.w_dir, m.group,
                               "6.2.11.3: укороченные балки крепятся на угловые металлические "
                               "накладки или гвоздями по табл. 6-1"))
    res.members[:] = keep
    return removed


# --------------------------------------------------------------------------
# 6.2.10 Консольные балки
# --------------------------------------------------------------------------
def cantilevers(res, spec: dict, plat: dict, group: str, items: list[dict]) -> None:
    """Консоли: {"side": "N"|"S"|"E"|"W", "overhang": м, "from": м, "to": м}."""
    if not items:
        return
    L, W = spec["plan"]["length"], spec["plan"]["width"]
    direction = spec["floor"]["direction"]
    sp = plat["spacing"]
    zc = plat["z_top"] - plat["subfloor_mm"] * MM - plat["depth"] / 2
    add = res.members.append

    for i, c in enumerate(items, 1):
        side = c["side"].upper()
        oh = float(c["overhang"])
        tag = f"консоль {i} ({side})"
        # сечение по 6.2.10.1
        if oh > 0.6:
            res.err(tag, f"вылет консоли {oh * 1000:.0f} мм > 600 мм — сечение балок "
                         f"определяется расчётом (6.2.10.1)")
            sec = c.get("section", "38x286")
        else:
            sec = c.get("section", "38x235")
            res.ok(tag, f"вылет {oh * 1000:.0f} мм ≤ 600 мм — сечение балок ≥38x235 "
                        f"(6.2.10.1, консоль несёт нагрузку от крыши)")
        if c.get("carries_storeys"):
            res.err(tag, "консоль несёт нагрузку не только от крыши, но и от этажей — "
                         "сечение определяется расчётом (6.2.10.2)")
        ct, cd = R.sec(sec)

        # консоль продолжает балки или перпендикулярна им?
        parallel = (direction == "y" and side in ("N", "S")) or \
                   (direction == "x" and side in ("E", "W"))
        a = float(c.get("from", 0.0))
        b = float(c.get("to", L if side in ("N", "S") else W))
        inner = max(6 * oh, 6 * oh)     # 6.2.10.3

        if parallel:
            n = extend_joists(res, spec, side, oh, a, b, sec)
            res.ok(tag, f"6.2.10: консоль — продолжение балок перекрытия; "
                        f"удлинено балок: {n}, сечение {sec}")
            continue
        res.ok(tag, f"6.2.10.3: консольные балки перпендикулярны балкам перекрытия — "
                    f"заводятся внутрь на ≥6 длин консоли ({inner:.2f} м) и прибиваются "
                    f"к внутренней сдвоенной балке перекрытия")
        for u in _positions(a, b, sp, ct):
            if side == "S":
                p1, p2 = (u, inner, zc), (u, -oh, zc)
            elif side == "N":
                p1, p2 = (u, W - inner, zc), (u, W + oh, zc)
            elif side == "W":
                p1, p2 = (inner, u, zc), (-oh, u, zc)
            else:
                p1, p2 = (L - inner, u, zc), (L + oh, u, zc)
            add(Member("cantilever", f"Консольная балка {sec}", (ct, cd), p1, p2, (0, 0, 1),
                       group, "6.2.10.3: заводится внутрь перекрытия на ≥6 длин консоли, "
                              "прибивается к внутренней сдвоенной балке"))


def _positions(a: float, b: float, spacing_mm: int, t_mm: int) -> list[float]:
    s = spacing_mm * MM
    out, u = [], a + t_mm * MM / 2
    while u <= b - t_mm * MM / 2 + 1e-9:
        out.append(round(u, 6))
        u += s
    return out


# --------------------------------------------------------------------------
# Раздел 12. Лестница
# --------------------------------------------------------------------------
def stairs(res, spec: dict, cfg: dict, z_from: float, z_to: float, group: str,
           z_upper_bottom: float | None = None) -> dict:
    """Прямой марш по разделу 12. cfg: {"x","y","dir","width"}.

    СП 31-105 нормирует ГАБАРИТЫ лестницы (табл. 12-1, 12.2.1), но НЕ сечение
    косоуров/тетив — оно определяется расчётом по СНиП II-25.
    """
    S = R.STAIR
    width = float(cfg.get("width", 1.0))
    direction = cfg.get("dir", "x")
    x, y = float(cfg.get("x", 1.0)), float(cfg.get("y", 1.0))
    total = z_to - z_from
    add = res.members.append

    n = max(1, math.ceil(total * 1000 / S["riser_max"]))
    riser = total * 1000 / n
    tread = float(cfg.get("tread", max(S["tread_min"], riser * 1.25)))

    if width * 1000 < S["width_min"]:
        res.err("лестница", f"ширина {width * 1000:.0f} мм < 900 мм (12.2.1.1)")
    else:
        res.ok("лестница", f"ширина {width * 1000:.0f} мм ≥ 900 мм (12.2.1.1)")
    if not (S["riser_min"] <= riser <= S["riser_max"]):
        res.err("лестница", f"высота ступени {riser:.0f} мм вне диапазона "
                            f"{S['riser_min']}–{S['riser_max']} мм (табл. 12-1)")
    else:
        res.ok("лестница", f"{n} подступёнков по {riser:.0f} мм "
                           f"({S['riser_min']}–{S['riser_max']} мм, табл. 12-1)")
    if not (S["tread_min"] <= tread <= S["tread_max"]):
        res.err("лестница", f"глубина проступи {tread:.0f} мм вне диапазона "
                            f"{S['tread_min']}–{S['tread_max']} мм (табл. 12-1)")
    else:
        res.ok("лестница", f"проступь {tread:.0f} мм "
                           f"({S['tread_min']}–{S['tread_max']} мм, табл. 12-1)")
    if n > S["risers_per_flight_max"]:
        res.err("лестница", f"{n} ступеней в марше > 18 — нужна промежуточная площадка "
                            f"(12.2.1.5, 12.2.2)")
    slope = riser / tread
    if slope > S["slope_max"] + 1e-6:
        res.warn("лестница", f"уклон 1:{tread / riser:.2f} круче рекомендованного 1:1,25 "
                             f"(12.2.1.2)")
    run = n * tread / 1000

    # 12.2.1.3: высота в свету ≥1,95 м -> отсюда требуемая длина проёма в перекрытии
    need_open = None
    if z_upper_bottom is not None:
        k = 0
        while k < n and (z_upper_bottom - (z_from + riser * k / 1000)) >= 1.95:
            k += 1
        need_open = max(0.0, (n - k) * tread / 1000)
        res.ok("лестница", f"длина марша в плане {run:.2f} м; для высоты в свету ≥1,95 м "
                           f"(12.2.1.3) проём в перекрытии нужен длиной ≥{need_open:.2f} м "
                           f"от {k}-й ступени")
    else:
        res.ok("лестница", f"длина марша в плане {run:.2f} м; проём в перекрытии должен "
                           f"обеспечить высоту в свету ≥1,95 м над выступом ступеней "
                           f"(12.2.1.3)")
    res.warn("лестница/несущая часть",
             "сечение косоуров (тетив) СП 31-105-2002 не нормирует — определяется "
             "расчётом по СНиП II-25; в модели показаны только ступени и проступи")

    for k in range(n):
        zt = z_from + riser * (k + 1) / 1000
        off = tread / 1000 * k
        if direction == "x":
            p1 = (x + off + tread / 2000, y, zt - 0.019)
            p2 = (x + off + tread / 2000, y + width, zt - 0.019)
            add(Member("tread", f"Проступь {int(tread)} мм", (int(tread), 38), p1, p2, (1, 0, 0),
                       group, "табл. 12-1: проступь 235–355 мм, высота ступени 125–200 мм"))
        else:
            p1 = (x, y + off + tread / 2000, zt - 0.019)
            p2 = (x + width, y + off + tread / 2000, zt - 0.019)
            add(Member("tread", f"Проступь {int(tread)} мм", (int(tread), 38), p1, p2, (0, 1, 0),
                       group, "табл. 12-1: проступь 235–355 мм, высота ступени 125–200 мм"))
    return {"n": n, "riser": riser, "tread": tread, "run": run, "width": width,
            "opening_min": need_open}


def extend_joists(res, spec: dict, side: str, oh: float, a: float, b: float,
                  sec: str) -> int:
    """Консоль как продолжение балок: удлиняет существующие балки за наружную грань."""
    L, W = spec["plan"]["length"], spec["plan"]["width"]
    ax = 1 if side in ("N", "S") else 0        # ось, вдоль которой идут балки
    target = {"S": 0.0, "N": W, "W": 0.0, "E": L}[side]
    out = -oh if side in ("S", "W") else oh
    jt, jd = R.sec(sec)
    n = 0
    for m in res.members:
        if m.kind not in ("joist", "rim"):
            continue
        along = m.p1[1 - ax]
        if not (a - 1e-6 <= along <= b + 1e-6):
            continue
        for attr in ("p1", "p2"):
            pt = list(getattr(m, attr))
            if abs(pt[ax] - target) < 1e-6:
                pt[ax] = target + out
                setattr(m, attr, tuple(pt))
                n += 1
                if m.section[1] < jd:
                    m.section = (m.section[0], jd)
                m.note += ("; 6.2.10.1: консольная часть — сечение ≥38x235 "
                           "при вылете до 600 мм")
    return n
