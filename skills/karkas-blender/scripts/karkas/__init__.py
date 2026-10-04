"""karkas — параметрический каркас дома по СП 31-105-2002 для Blender."""
from . import rules, geom, model          # noqa: F401
from .model import build_house, report, bom, merge_spec, DEFAULT_SPEC   # noqa: F401

__all__ = ["rules", "geom", "model", "build_house", "report", "bom",
           "merge_spec", "DEFAULT_SPEC"]
__version__ = "1.0.0"
