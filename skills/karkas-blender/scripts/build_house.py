#!/usr/bin/env python3
"""CLI: построить каркас по спецификации.

Пути к скрипту и спецификации можно давать любые — скрипт сам находит свой каталог,
а --spec принимает либо путь, либо имя готового примера из examples/.

Внутри Blender (создаёт .blend, рендер, ведомость):
    blender -b --python <skill>/scripts/build_house.py -- \
        --spec dom_9x7 --out out/dom --render --views iso,front,top

Без Blender (только проверка по СП + ведомость материалов):
    python3 <skill>/scripts/build_house.py --spec dom_9x7 --check
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from karkas.model import build_house, report, bom   # noqa: E402


def argv_after_dashdash() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def parse_args():
    p = argparse.ArgumentParser(description="Каркасный дом по СП 31-105-2002")
    p.add_argument("--spec", help="JSON-файл спецификации (иначе — умолчания)")
    p.add_argument("--set", action="append", default=[],
                   help="переопределение: --set plan.width=8 --set roof.slope=1:1.71")
    p.add_argument("--out", default="out/karkas", help="префикс выходных файлов")
    p.add_argument("--check", action="store_true", help="только проверка, без Blender")
    p.add_argument("--render", action="store_true", help="отрендерить PNG")
    p.add_argument("--views", default="iso", help="ракурсы через запятую: iso,front,side,top")
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--resolution", default="1920x1080")
    p.add_argument("--no-save", action="store_true", help="не сохранять .blend")
    p.add_argument("--open", action="store_true",
                   help="открыть результат в Blender GUI, если он ещё не открыт "
                        "(дальше файл перечитывается сам аддоном karkas_autoreload)")
    p.add_argument("--strict", action="store_true",
                   help="завершиться с кодом 1 при любой ошибке соответствия СП")
    return p.parse_args(argv_after_dashdash())


def apply_overrides(spec: dict, items: list[str]) -> dict:
    for it in items:
        path, _, val = it.partition("=")
        try:
            v = json.loads(val)
        except json.JSONDecodeError:
            v = val
        node = spec
        keys = path.split(".")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = v
    return spec


def write_outputs(res, out_prefix: str) -> dict:
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    rep = report(res)
    with open(out_prefix + "_report.txt", "w", encoding="utf-8") as f:
        f.write(rep + "\n")
    rows = bom(res.members)
    with open(out_prefix + "_bom.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "section", "length_m", "count",
                                          "total_m", "volume_m3"])
        w.writeheader()
        w.writerows(rows)
    with open(out_prefix + "_members.json", "w", encoding="utf-8") as f:
        json.dump([{"kind": m.kind, "label": m.label, "section": m.sec_str,
                    "p1": m.p1, "p2": m.p2, "w_dir": m.w_dir, "group": m.group,
                    "length_m": round(m.length, 4), "note": m.note}
                   for m in res.members], f, ensure_ascii=False, indent=1)
    return {"report": out_prefix + "_report.txt", "bom": out_prefix + "_bom.csv",
            "members": out_prefix + "_members.json", "text": rep}


SKILL_DIR = os.path.dirname(HERE)          # каталог скилла (на уровень выше scripts/)


def resolve_spec(path: str) -> str:
    """--spec принимает путь, либо имя примера: 'dom_9x7' / 'dom_9x7.json'."""
    if os.path.isfile(path):
        return path
    for cand in (path, path + ".json"):
        p = os.path.join(SKILL_DIR, "examples", os.path.basename(cand))
        if os.path.isfile(p):
            return p
    raise SystemExit(f"спецификация не найдена: {path}\n"
                     f"доступные примеры: "
                     + ", ".join(sorted(os.listdir(os.path.join(SKILL_DIR, "examples")))))


BLENDER_APP = "/Applications/Blender.app/Contents/MacOS/Blender"


def blender_gui_pids(blend: str) -> list[str]:
    """PID GUI-процессов Blender, у которых открыт именно этот файл."""
    import subprocess
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="],
                             capture_output=True, text=True).stdout
    except OSError:
        return []
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if "Blender" not in line or "/MacOS/Blender" not in line and "blender" not in line:
            continue
        parts = line.split()
        if len(parts) < 2 or "-b" in parts or "--background" in parts:
            continue
        if blend in line:
            pids.append(parts[0])
    return pids


def ensure_open(blend: str) -> str:
    """Открыть .blend в GUI, если ни один GUI-инстанс его не держит."""
    import subprocess
    pids = blender_gui_pids(blend)
    if pids:
        return f"уже открыт в Blender (pid {', '.join(pids)}): {blend}"
    if sys.platform == "darwin" and os.path.exists("/Applications/Blender.app"):
        cmd = ["open", "-na", "/Applications/Blender.app", "--args", blend]
    else:
        cmd = [os.environ.get("BLENDER", "blender"), blend]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return f"запущен Blender с файлом: {blend}"
    except OSError as e:
        return f"не удалось открыть Blender ({e}); откройте вручную: {blend}"


def main():
    a = parse_args()
    spec = json.load(open(resolve_spec(a.spec), encoding="utf-8")) if a.spec else {}
    spec = apply_overrides(spec, a.set)

    res = build_house(spec)
    files = write_outputs(res, a.out)
    print(files["text"])
    print()
    for k, v in files.items():
        if k != "text":
            print(f"записано: {v}")

    if not a.check:
        try:
            import bpy   # noqa: F401
        except ImportError:
            print("\n[i] bpy недоступен — геометрия не построена. "
                  "Запустите через Blender или добавьте --check.", file=sys.stderr)
        else:
            from karkas import build as kb
            kb.clear_scene()
            built = kb.build(res)
            objs = built["objects"]
            print(f"\nпостроено объектов: {len(objs)}")
            if not a.no_save:
                import bpy
                blend = os.path.abspath(a.out + ".blend")
                bpy.ops.wm.save_as_mainfile(filepath=blend)
                print(f"записано: {blend}")
            if a.open:
                print(ensure_open(blend if not a.no_save else os.path.abspath(a.out + ".blend")))
            if a.render:
                w, h = (int(x) for x in a.resolution.lower().split("x"))
                for view in a.views.split(","):
                    view = view.strip()
                    for o in list(bpy.data.objects):
                        if o.type in {"CAMERA", "LIGHT"}:
                            bpy.data.objects.remove(o, do_unlink=True)
                    kb.setup_scene(objs, view=view, resolution=(w, h))
                    png = os.path.abspath(f"{a.out}_{view}.png")
                    kb.render(png, samples=a.samples)
                    print(f"записано: {png}")

    if a.strict and res.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
