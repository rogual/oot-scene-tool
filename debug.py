from .utils import object_bounds


def dump_scene(scene):
    print()
    print('Rooms:')
    for room in scene.rooms:
        print(f'  {room}')
        print(f'    f64 obj = {room.fast64_object}')
        print(f'    bounds = {room.geometry_bounds}')
        print(f'    geometry objects:')
        for obj in room.geometry_objects:
            print(f'      {obj}')
            print(f'      bounds = {object_bounds(obj)}')
        for layer in room.layers:
            print(f'    {layer}')
