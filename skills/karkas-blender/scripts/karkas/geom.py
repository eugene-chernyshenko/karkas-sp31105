"""Базовый элемент каркаса — прямоугольный брус, заданный осью и сечением."""
from __future__ import annotations
from dataclasses import dataclass, field
import math

Vec = tuple[float, float, float]


def vsub(a: Vec, b: Vec) -> Vec: return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def vadd(a: Vec, b: Vec) -> Vec: return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def vmul(a: Vec, k: float) -> Vec: return (a[0] * k, a[1] * k, a[2] * k)
def vlen(a: Vec) -> float: return math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)


def vnorm(a: Vec) -> Vec:
    L = vlen(a)
    if L < 1e-12:
        raise ValueError("нулевой вектор")
    return (a[0] / L, a[1] / L, a[2] / L)


def vcross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


@dataclass
class Member:
    """Брус: ось p1→p2 (центры торцов), сечение (t, h) в мм.

    t откладывается вдоль w_dir, h — вдоль (axis × w_dir).
    Длина берётся по оси; это чистовая длина элемента в модели.
    """
    kind: str                 # машинный тип: stud, plate, header, joist, rafter, ...
    label: str                # человекочитаемое название по СП
    section: tuple[int, int]  # мм
    p1: Vec
    p2: Vec
    w_dir: Vec
    group: str = "Каркас"     # коллекция в Blender
    note: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def length(self) -> float:
        return vlen(vsub(self.p2, self.p1))

    @property
    def axis(self) -> Vec:
        return vnorm(vsub(self.p2, self.p1))

    @property
    def center(self) -> Vec:
        return vmul(vadd(self.p1, self.p2), 0.5)

    @property
    def basis(self) -> tuple[Vec, Vec, Vec]:
        """(вдоль оси, вдоль t, вдоль h) — ортонормированный правый базис."""
        x = self.axis
        w = vnorm(vsub(self.w_dir, vmul(x, sum(a * b for a, b in zip(x, self.w_dir)))))
        h = vcross(x, w)
        return x, w, h

    @property
    def size(self) -> Vec:
        return (self.length, self.section[0] / 1000.0, self.section[1] / 1000.0)

    @property
    def volume(self) -> float:
        return self.length * self.section[0] * self.section[1] / 1e6

    @property
    def sec_str(self) -> str:
        return f"{self.section[0]}x{self.section[1]}"


def offset_member(m: Member, v: Vec) -> Member:
    from dataclasses import replace
    return replace(m, p1=vadd(m.p1, v), p2=vadd(m.p2, v))
