from . import app
from .common_utils import *

try:
    log_to_file('/tmp/ootlog.txt')
except FileNotFoundError:
    # Perhaps a Windows user can contribute a suitable log file path?
    # For now, we just won't log on Windows. Add your own path here
    # if you need to debug the tool.
    # log_to_file(r"C:\Blah\OOT Scene Tool Log.txt")
    pass


import bpy
import functools
import mathutils

def clear_collection(coll):
    for obj in coll.objects:
        coll.objects.unlink(obj)
        obj.parent = None
        print("REMOVE", obj)
        bpy.data.objects.remove(obj) 

    for ch in coll.children:
        clear_collection(ch)
        coll.children.unlink(ch)
        bpy.data.collections.remove(ch)

    
def empty_collection(name, parent=None):
    if coll := bpy.data.collections.get(name):
        clear_collection(coll)
    else:
        coll = bpy.data.collections.new(name)


    if not parent:
        parent = bpy.context.scene.collection

    try:
        parent.children.link(coll)
    except:
        pass

    return coll


def move_to_collection(obj, collection):
    collection.objects.link(obj)
    try:
        bpy.context.scene.collection.objects.unlink(obj)
    except:
        pass
    

def descendants(obj):
    for x in obj.children:
        yield x
        yield from descendants(x)


def points_bounds(cos):
    axis_vals = [
        [co[axis] for co in cos]
        for axis in [0, 1, 2]
    ]
    
    return Bounds([
        Range(min(vals), max(vals))
        for vals in axis_vals
    ])


def object_bounds(obj):
    return points_bounds([
        obj.matrix_world @ mathutils.Vector(v) 
        for v in obj.bound_box
    ])


def objects_bounds(objs):
    return functools.reduce(
        bounds_union,
        map(object_bounds, objs),
        Bounds(),
    )


def duplicate_object(obj, collection):
    new_obj = obj.copy()
    for coll in new_obj.users_collection:
        coll.objects.unlink(new_obj)
    collection.objects.link(new_obj)
    new_obj.data = new_obj.data.copy()
    return new_obj


def clip_object(obj1, obj2):
    mod = obj1.modifiers.new('mod', 'BOOLEAN')
    mod.operation = 'INTERSECT'
    mod.object = obj2
    mod.use_hole_tolerant = True
    mod.use_self = True
    #bpy.ops.object.modifier_apply(apply_as='DATA', modifier='mod')


def map_rect(from_rect, to_rect):
    ax0, ay0 = from_rect.origin
    bx0, by0 = to_rect.origin

    aw, ah = from_rect.size
    bw, bh = to_rect.size

    return mathutils.Matrix([
        [bw/aw,     0,    bx0 - ax0 * bw/aw],
        [    0, bh/ah,    by0 - ay0 * bh/ah],
        [    0,     0,                     1]
    ])

        


class Image:
    def __init__(self, key):
        self.key = key

    @property
    def name(self):
        return '_'.join(map(str, self.key))

    @property
    def render_path(self):
        os.makedirs(app.scene.render_dir, exist_ok=True)
        return f'{app.scene.render_dir}/{self.name}.png'
