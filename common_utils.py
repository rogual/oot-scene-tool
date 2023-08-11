from dataclasses import dataclass
from functools import cached_property

import os
import sys


log_file = None
def log_to_file(path):
    global log_file
    log_file = open(path, 'wt')
    sys.stdout = log_file
    sys.stderr = log_file


def cache_as_property(property_name):
    def decorator(fn):
        def wrap(a1, *a, **kw):
            if hasattr(a1, property_name):
                return getattr(a1, property_name)
            r = fn(a1, *a, **kw)
            setattr(a1, property_name, r)
            return r
        return wrap
    return decorator


def log(*a, **kw):
    if 'file' in kw:
        print(*a, **kw)
    elif log_file:
        print(*a, **kw, file=log_file)
        log_file.flush()
    else:
        print(*a, **kw)


def index_where(xs, p):
    return next(i for i, x in enumerate(xs) if p(x))


def yield_list(fn):
    def wrap(*a, **kw):
        return list(fn(*a, **kw))
    wrap.__name__ = fn.__name__
    return wrap


def pad_back(xs, n, pad):
    npad = n - len(xs)
    if npad > 0:
        return xs + [pad] * npad
    return xs


def pad_front(xs, n, pad):
    npad = n - len(xs)
    if npad > 0:
        return [pad] * npad + xs
    return xs


@dataclass
class Vec2:
    x: float
    y: float

    def __getitem__(self, i):
        return [self.x, self.y][i]

    def __setitem__(self, i, v):
        if i == 0: self.x = v
        elif i == 1: self.y = v
        else: raise IndexError(i)

    def __add__(self, o):
        return Vec2(self.x + o.x, self.y + o.y)

    def __sub__(self, o):
        return Vec2(self.x - o.x, self.y - o.y)

    def __mul__(self, f):
        return Vec2(self.x * f, self.y * f)

    def __iter__(self):
        return iter([self.x, self.y])


@dataclass
class Vec3:
    x: float
    y: float
    z: float

    def __getitem__(self, i):
        return [self.x, self.y, self.z][i]

    def __setitem__(self, i, v):
        if i == 0: self.x = v
        elif i == 1: self.y = v
        elif i == 2: self.z = v
        else: raise IndexError(i)


@dataclass
class Range:
    a: float = float('inf')
    b: float = float('-inf')

    def __getitem__(self, i):
        return [self.a, self.b][i]

    def __bool__(self):
        return not self.empty

    def __str__(self):
        return f'{self.a}:{self.b}'

    @property
    def min(self):
        return self.a
    
    @property
    def max(self):
        return self.b

    @property
    def size(self):
        if self.empty:
            return None
        return self.b - self.a

    def union(self, o):
        return Range(
            min(self.a, o.a),
            max(self.b, o.b)
        )

    def intersection(self, o):
        return Range(
            max(self.a, o.a),
            min(self.b, o.b)
        )

    def contains(self, x):
        return self.a <= x and x < self.b

    @property
    def empty(self):
        return self.b < self.a

    @property
    def center(self):
        return self.a + (self.b - self.a) / 2


class Bounds:
    axes: list[Range]

    def __str__(self):
        return f'{self.axes}'

    def contains(self, point):
        return all(
            axis.contains(coord)
            for axis, coord in zip(self.axes, point)
        )

    @property
    def x(self):
        return self.axes[0]

    @property
    def y(self):
        return self.axes[1]

    @property
    def z(self):
        return self.axes[2]
    
    def __init__(self, axes=None):
        if axes is None:
            axes = [Range(), Range(), Range()]
        self.axes = axes

    def union(self, o):
        return Bounds([
            self.axes[i].union(o.axes[i])
            for i in range(3)
        ])
    
    def intersection(self, o):
        return Bounds([
            self.axes[i].intersection(o.axes[i])
            for i in range(3)
        ])

    @property
    def empty(self):
        return any(axis.empty for axis in self.axes)

    @property
    def center(self):
        return Vec3(*[
            a.center
            for a in self.axes
        ])

    def __bool__(self):
        return not self.empty


def bounds_union(a, b): return a.union(b)
def bounds_intersection(a, b): return a.intersection(b)

@dataclass
class Rect:
    origin: Vec2
    size: Vec2

    @classmethod
    def centered(cls, c, size):
        return Rect(
            c - size * .5,
            size
        )

    @property
    def min(self):
        return self.origin

    @min.setter
    def min(self, p):
        self.origin = p

    @property
    def max(self):
        return self.origin + self.size

    @max.setter
    def max(self, p):
        self.size = p - self.origin

    @classmethod
    def bounding_points(cls, *points):
        log('bp', points)
        r = Rect(
            points[0],
            Vec2(0, 0)
        )
        for p in points[1:]:
            r = r.bounds_union(Rect(p, Vec2(1, 1)))
        return r

    def bounds_union(self, o):
        log(self, o, self.min, o.min)
        x0 = min(self.min.x, o.min.x)
        x1 = max(self.max.x, o.max.x)
        y0 = min(self.min.y, o.min.y)
        y1 = max(self.max.y, o.max.y)
        return Rect(Vec2(x0, y0), Vec2(x1 - x0, y1 - y0))

    def expand(self, v):
        r = Rect(self.origin, self.size)
        r.origin = r.origin - Vec2(v, v)
        r.size = r.size + Vec2(2*v, 2*v)
        return r

    def __add__(self, v):
        return Rect(
            self.origin + v,
            self.size
        )
        
