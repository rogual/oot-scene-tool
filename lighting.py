import bpy
import random
from .utils import *


def color_mul(a, b):
    return tuple([
        a[i] * b[i]
        for i in range(4)
    ])


def color_add(dest, a, b):
    for i in range(3):
        dest[i] = a[i] + b[i]


def merge_vertex_colors(scene):
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            if obj.data.color_attributes.get('Multiply'):
                merge_vertex_colors_for_object(obj)


def merge_vertex_colors_for_object(geom_obj):
    mesh = geom_obj.data

    layer_col = mesh.color_attributes['Col']
    layer_ao = mesh.color_attributes['AO']
    layer_mul = mesh.color_attributes['Multiply']

    log('col', len(layer_col.data))
    log('ao', len(layer_ao.data))
    log('mul', len(layer_mul.data))

    i = 0
    for poly in mesh.polygons:
        for idx in poly.loop_indices:
            if i < len(layer_col.data):

                if i < len(layer_mul.data):
                    mul = layer_mul.data[i].color
                else:
                    mul = (1, 1, 1, 1)

                if i < len(layer_ao.data):
                    ao = layer_ao.data[i].color
                else:
                    ao = (1, 1, 1, 1)

                layer_col.data[i].color = color_mul(mul, ao)

            i += 1
