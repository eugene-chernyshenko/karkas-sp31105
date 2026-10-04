#!/usr/bin/env bash
# Ставит аддон автоперезагрузки в Blender и включает его.
# Открытый .blend будет сам перечитываться после каждой пересборки.
set -euo pipefail

BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
[ -x "$BLENDER" ] || { echo "Blender не найден: $BLENDER (задайте BLENDER=...)"; exit 1; }

VER=$("$BLENDER" --version | head -1 | awk '{print $2}' | cut -d. -f1,2)
case "$(uname -s)" in
  Darwin) CFG="$HOME/Library/Application Support/Blender/$VER/scripts/addons" ;;
  *)      CFG="$HOME/.config/blender/$VER/scripts/addons" ;;
esac

mkdir -p "$CFG"
cp "$(dirname "$0")/karkas_autoreload.py" "$CFG/"
"$BLENDER" -b --python-expr "
import bpy
bpy.ops.preferences.addon_enable(module='karkas_autoreload')
bpy.ops.wm.save_userpref()
" >/dev/null 2>&1

echo "аддон установлен: $CFG/karkas_autoreload.py"
echo "журнал перезагрузок: ~/.cache/karkas/autoreload.log"
