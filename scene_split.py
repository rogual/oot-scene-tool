import mathutils
import bmesh

from .utils import *


@cache_as_property('_scene_split_catchment_boxes')
@yield_list
def room_catchment_boxes(room):
    i = 0
    for child in room.fast64_object.children:
        if 'Bounds' in child.name:
            child.name = f'Bounds{room.index}.{i}'
            i += 1
            yield child


def can_split(scene):
    return 'Geom' in bpy.data.objects

    
def split(scene):

    # The object to split into rooms
    # TODO: Make this selectable
    geom_obj = bpy.data.objects['Geom']


    collection = scene.helper_collection('Split Room Geometry')

    # TODO: Figure out why this needs to happen. If helpers are
    # hidden, splitter fails to split anything. Why is evrything
    # in Blender dependent on UI state. It's brittle and shitty.
    # You just end up with code sprinkled with magic invocations
    # like this and you have no idea how anything works.
    scene.helpers.hide_viewport = False

    for obj in bpy.data.objects:
        if 'ExpGen' in obj.name:
            obj.parent = None
            bpy.data.objects.remove(obj) 

    for face in geom_obj.data.polygons:
        face.hide = False

    for room in scene.rooms:
        room_geom = duplicate_object(geom_obj, collection)
        room_geom.name = f'ExpGen {room} Geometry'

        # Reparent to fast64_obj
        for vertex in room_geom.data.vertices:
            vertex.co = (
                geom_obj.matrix_world @ vertex.co -
                (room.fast64_object.matrix_world @ mathutils.Vector((0,0,0)))
            )
        room_geom.location = (0, 0, 0)
        room_geom.parent = room.fast64_object

        cull(room, room_geom)

        if len(room_geom.data.vertices) == 0:
            raise Exception("Room {room} has no vertices")


def cull(room, geom):
    mesh = geom.data
    log('culling', geom.name, 'to', room, '; mesh', mesh, 'npoly', len(mesh.polygons))

    catchment_boxes = room_catchment_boxes(room)
    log(len(catchment_boxes), 'catchment boxes')

    started_with = len(mesh.polygons)
    
    bpy.context.view_layer.update()


    geom.hide_viewport = False

    for obj in bpy.data.objects:
        obj.select_set(False)

    geom.select_set(True)
    bpy.context.view_layer.objects.active = geom

    bpy.ops.object.mode_set(mode = 'OBJECT', toggle=False) 

    bm = bmesh.new()
    bm.from_mesh(mesh)

    bm.faces.ensure_lookup_table()

    faces_to_delete=[
        face for face in bm.faces if not any(
            bounds_intersection(
                object_bounds(catchment_box),
                face_bounds(geom, face)
            )
            for catchment_box in catchment_boxes
        )
    ]

    bmesh.ops.delete(
        bm,
        geom=faces_to_delete,
        context='FACES'
    )

    bm.to_mesh(mesh)

    log('culled', geom.name, mesh, '; result npoly = ', len(mesh.polygons))

    assert len(mesh.polygons) == started_with - len(faces_to_delete)


def face_bounds(obj, bm_face):
    cos = [
        obj.matrix_world @ vert.co
        for vert in bm_face.verts
    ]
    
    return points_bounds(cos)


def polygon_bounds(obj, mesh, polygon):
    
    cos = [
        obj.matrix_world @ mathutils.Vector(mesh.vertices[i].co)
        for i in polygon.vertices
    ]
    
    return points_bounds(cos)


def move_actors_to_their_rooms(scene):
    move = {}
    for actor in scene.actors:
        for room in scene.rooms:
            if room.fast64_object != actor.parent:
                for box in room_catchment_boxes(room):
                    pos = actor.matrix_world.translation
                    bounds = object_bounds(box)
                    if bounds.contains(pos):
                        move[actor] = room

    for actor, room in move.items():
        log(f"Move {actor} to {room}")

        mw = actor.matrix_world
        actor.parent = room.fast64_object
        actor.matrix_world = mw
        

                
