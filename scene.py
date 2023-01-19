import itertools
import os
import functools

import bpy
import mathutils

from . import z64c

from .utils import *


class Scene:
    def __init__(self, blender_scene):
        fast64_scene_object = blender_scene.ootSceneExportObj
        fast64_scene_option = blender_scene.ootSceneExportSettings.option
        fast64_oot_path = blender_scene.ootDecompPath

        self.blender_scene = blender_scene
        self.fast64_object = fast64_scene_object
        self.oot_path = os.path.abspath(bpy.path.abspath(fast64_oot_path))

        self.helpers = empty_collection("OOT Scene Tool Helper Objects")
        self.helper_collections = {}

        self.display_name = "Temple of Sadness"

    @cached_property
    def index(self):
        return z64c.get_scene_index(self.oot_path, fast64_scene_option)

    def blender_to_oot_pos(self, blender_pos):
        scale = self.blender_scene.ootBlenderScale
        return mathutils.Vector((
            blender_pos.x * scale,
            blender_pos.z * scale,
            blender_pos.y * scale * -1
        ))

    def helper_collection(self, name, parent=None):
        if name in self.helper_collections:
            return self.helper_collections[name]

        collection = self.helper_collections[name] = empty_collection(
            name,
            parent=parent or self.helpers
        )
        return collection

    @cached_property
    def bounds(self):
        return objects_bounds([
            obj
            for room in self.rooms
            for obj in room.geometry_objects
        ])

    @cached_property
    def center(self):
        return self.bounds.center

    @cached_property
    @yield_list
    def actors(self):
        for room in self.rooms:
            yield from room.actors

    @cached_property
    def floors(self):
        if coll := bpy.data.collections.get('Floor Planes'):
            floor_planes = list(sorted(obj.location.z for obj in coll.objects))
        else:
            floor_planes = []

        ztop = 5000

        planes = floor_planes + [ztop]

        return [
            Floor(index, low, high)
            for index, (low, high) in enumerate(itertools.pairwise(planes))
        ]

    @cached_property
    def rooms(self):
        return [
            Room(obj)
            for obj in self.fast64_object.children
            if obj.type == 'EMPTY' and obj.ootEmptyType == 'Room'
        ]

    # TODO: Remove
    def get_room(self, index):
        for room in self.rooms:
            if room.index == index:
                return room
        raise Exception()



class Room:
    def __init__(self, fast64_object):
        self.fast64_object = fast64_object

    def __str__(self):
        return f"Room {self.index}"

    @property
    def index(self):
        return self.fast64_object.ootRoomHeader.roomIndex

    @property
    def geometry_objects(self):
        return [
            x for x in descendants(self.fast64_object)
            if x.type == 'MESH'
            and not x.ignore_render
        ]

    @cached_property
    def geometry_bounds(self):
        return objects_bounds(self.geometry_objects)

    @cached_property
    def layers(self):
        bounds = self.geometry_bounds

        return [
            Layer(self, floor)
            for floor in scene.floors
            if floor.z_range.intersection(bounds.z)
        ]

    @cached_property
    def actors(self):
        return [
            x for x in descendants(self.fast64_object)
            if x.type == 'EMPTY'
            and x.ootEmptyType == 'Actor'
        ]


class Layer:
    def __init__(self, room, floor):
        self.room = room
        self.floor = floor

    def __str__(self):
        return f'{self.room} {self.floor}'

    @property
    def index_in_room(self):
        return self.room.layers.index(self)

    @cached_property
    def actors(self):
        z0, z1 = self.floor.z_range
        return [
            actor for actor
            in self.room.actors
            if z0 <= actor.matrix_world.translation.z < z1
        ]


class Floor:
    def __init__(self, index, z0, z1):
        self.index = index
        self.z0 = z0
        self.z1 = z1
        self.height = z1 - z0
        self.z_center = z0 + (z1 - z0) / 2
        self.z_range = Range(z0, z1)

    def __str__(self):
        return f'Floor {self.index}'

    @cached_property
    def volume_object(self):
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(0, 0, self.z_center),
            scale=(800, 800, self.height)
        )
        obj = bpy.context.view_layer.objects.active
        obj.name = f'Floor Volume {self.index}'
        obj.display_type = 'WIRE'

        # TODO: Create this material
        mat_void = bpy.data.materials['DMVoid']

        obj.data.materials.clear()
        obj.data.materials.append(mat_void)

        move_to_collection(obj, scene.helper_collection('Floor Volumes'))
        return obj

    @cached_property
    def layers(self):
        return [
            layer
            for room in scene.rooms
            for layer in room.layers
            if layer.floor is self
        ]

    @cached_property
    def rooms(self):
        return list(sorted(set(
            layer.room
            for layer in self.layers
        ), key=lambda room: room.index))

    @cached_property
    @yield_list
    def actors(self):
        for room in self.rooms:
            for layer in room.layers:
                if layer.floor is self:
                    yield from layer.actors

                    
