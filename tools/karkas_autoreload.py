bl_info = {
    "name": "Karkas Auto-Reload",
    "description": "Перечитывает открытый .blend, когда он пересобран на диске",
    "author": "karkas-sp31105",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "category": "System",
}

import os
import time

import bpy

INTERVAL = 1.5          # период опроса, с
LOG = os.path.join(os.path.expanduser("~"), ".cache", "karkas", "autoreload.log")
_state = {"path": None, "mtime": None, "skipped_dirty": False}


def _report(msg: str):
    print(f"[karkas-autoreload] {msg}")
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except OSError:
        pass
    wm = bpy.context.window_manager
    for win in getattr(wm, "windows", []):
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.header_text_set(msg)
                return


def _tick():
    path = bpy.data.filepath
    if not path or not os.path.exists(path):
        _state.update(path=None, mtime=None)
        return INTERVAL

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return INTERVAL

    if _state["path"] != path:
        _state.update(path=path, mtime=mtime, skipped_dirty=False)
        return INTERVAL

    if _state["mtime"] is None or mtime <= _state["mtime"]:
        return INTERVAL

    # файл пересобран на диске
    if bpy.data.is_dirty:
        if not _state["skipped_dirty"]:
            _report("файл пересобран, но в сцене есть несохранённые правки — "
                    "перезагрузка пропущена (File > Revert вручную)")
            _state["skipped_dirty"] = True
        return INTERVAL

    _state.update(mtime=mtime, skipped_dirty=False)
    try:
        bpy.ops.wm.revert_mainfile()
        _report(f"модель перезагружена: {os.path.basename(path)}")
    except RuntimeError as e:
        _report(f"не удалось перезагрузить: {e}")
    return INTERVAL


@bpy.app.handlers.persistent
def _on_load(_dummy):
    path = bpy.data.filepath
    _state.update(path=path or None,
                  mtime=os.path.getmtime(path) if path and os.path.exists(path) else None,
                  skipped_dirty=False)


def register():
    if bpy.app.background:      # в фоновых сборках следить не за чем
        return
    _report("автоперезагрузка включена")
    bpy.app.handlers.load_post.append(_on_load)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=INTERVAL, persistent=True)
    # bpy.data на этапе register() ограничен — состояние инициализирует первый тик


def unregister():
    if bpy.app.background:
        return
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
