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


